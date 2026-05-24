import discord
from discord import app_commands
import asyncio
import requests
import uuid
import time
import datetime
import os

# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("TOKEN")

GUILD_ID = 1504178459902087188

LTC_WALLET = "LaT5RZkkpviHSkbYwvFDcmczhv8w624A5b"

BUYER_ROLE_NAME = "Buyer"

STAFF_ROLE_ID = 1504178640093712475

USD_AMOUNT = 10
CHECK_INTERVAL = 20

# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# =========================================================
# BOT
# =========================================================

class MyBot(discord.Client):

    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):

        guild = discord.Object(id=GUILD_ID)

        self.tree.copy_global_to(guild=guild)

        await self.tree.sync(guild=guild)

bot = MyBot()

# =========================================================
# STORAGE
# =========================================================

escrow_sessions = {}

# =========================================================
# PRICE
# =========================================================

def get_ltc_price():

    r = requests.get(
        "https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd"
    ).json()

    return r["litecoin"]["usd"]

def usd_to_ltc(usd):

    return round(usd / get_ltc_price(), 6)

# =========================================================
# CHECK PAYMENT
# =========================================================

def get_new_payment(address, created_time):

    url = f"https://api.blockcypher.com/v1/ltc/main/addrs/{address}/full"

    data = requests.get(url).json()

    total = 0

    for tx in data.get("txs", []):

        confirmed = tx.get("confirmed")

        if not confirmed:
            continue

        tx_timestamp = datetime.datetime.fromisoformat(
            confirmed.replace("Z", "+00:00")
        ).timestamp()

        # ONLY count txs AFTER ticket creation
        if tx_timestamp < created_time:
            continue

        for out in tx.get("outputs", []):

            if address in out.get("addresses", []):

                total += out.get("value", 0)

    return total / 1e8

# =========================================================
# CLOSE TICKET
# =========================================================

class CloseTicketView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close Ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_message(
            "🔒 Closing ticket in 3 seconds...",
            ephemeral=True
        )

        await asyncio.sleep(3)

        await interaction.channel.delete()

# =========================================================
# PAYMENT BUTTONS
# =========================================================

class PaymentButtons(discord.ui.View):

    def __init__(self, expected_ltc):
        super().__init__(timeout=None)

        self.expected_ltc = expected_ltc

    @discord.ui.button(
        label="Copy Payment Info",
        emoji="📋",
        style=discord.ButtonStyle.secondary
    )
    async def copy_info(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_message(
            f"""
📥 Wallet Address:
`{LTC_WALLET}`

💰 Amount:
`{self.expected_ltc} LTC`
""",
            ephemeral=True
        )

    @discord.ui.button(
        label="Close Ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_message(
            "🔒 Closing ticket in 3 seconds...",
            ephemeral=True
        )

        await asyncio.sleep(3)

        await interaction.channel.delete()

# =========================================================
# START ESCROW
# =========================================================

async def start_escrow(channel, user):

    session_id = str(uuid.uuid4())[:8]

    expected_ltc = usd_to_ltc(USD_AMOUNT)

    escrow_sessions[session_id] = {
        "user_id": user.id,
        "channel_id": channel.id,
        "expected_ltc": expected_ltc,
        "paid": False,
        "created": time.time()
    }

    embed = discord.Embed(
        color=0x2b2d31
    )

    embed.add_field(
        name="<:ltc:1507880812643614972> • Secure Litecoin Checkout •",
        value="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        inline=False
    )

    embed.add_field(
        name="💰 Payment",
        value=f"${USD_AMOUNT} USD",
        inline=True
    )

    embed.add_field(
        name="🪙 LTC Amount",
        value=f"{expected_ltc} LTC",
        inline=True
    )

    embed.add_field(
        name="📥 Wallet",
        value=f"`{LTC_WALLET}`",
        inline=False
    )

    embed.add_field(
        name="🆔 Session ID",
        value=f"`{session_id}`",
        inline=False
    )

    embed.add_field(
        name="⚠ Status",
        value="Waiting for blockchain payment...",
        inline=False
    )

    embed.set_footer(
        text="Automatic blockchain verification enabled."
    )

    await channel.send(
        embed=embed,
        view=PaymentButtons(expected_ltc)
    )

    await monitor_escrow(channel, session_id)

# =========================================================
# MONITOR PAYMENT
# =========================================================

async def monitor_escrow(channel, session_id):

    session = escrow_sessions[session_id]

    while True:

        try:

            paid = get_new_payment(
                LTC_WALLET,
                session["created"]
            )

            if (
                paid >= session["expected_ltc"]
                and not session["paid"]
            ):

                session["paid"] = True

                guild = channel.guild

                member = guild.get_member(
                    session["user_id"]
                )

                role = discord.utils.get(
                    guild.roles,
                    name=BUYER_ROLE_NAME
                )

                if role:

                    await member.add_roles(role)

                embed = discord.Embed(
                    color=0x2ecc71
                )

                embed.add_field(
                    name="✅ • Payment Confirmed •",
                    value="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                    inline=False
                )

                embed.add_field(
                    name="User",
                    value=member.mention,
                    inline=False
                )

                embed.add_field(
                    name="Status",
                    value="Buyer role assigned successfully.",
                    inline=False
                )

                await channel.send(embed=embed)

                return

        except Exception as e:

            print("Payment Error:", e)

        await asyncio.sleep(CHECK_INTERVAL)

# =========================================================
# LTC PANEL
# =========================================================

class LitecoinPanel(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Pay with LTC",
        emoji="<:ltc:1507880812643614972>",
        style=discord.ButtonStyle.secondary
    )
    async def ltc_pay(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        guild = interaction.guild

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                read_messages=False
            ),

            interaction.user: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True
            )
        }

        channel = await guild.create_text_channel(
            name=f"ltc-{interaction.user.name}",
            overwrites=overwrites
        )

        await interaction.response.send_message(
            f"✅ Ticket opened: {channel.mention}",
            ephemeral=True
        )

        await start_escrow(channel, interaction.user)

# =========================================================
# BRAINROT PANEL
# =========================================================

class BrainrotPanel(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Pay with Brainrots",
        emoji="<:brainrot:1507881329499570246>",
        style=discord.ButtonStyle.secondary
    )
    async def brainrot_pay(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        guild = interaction.guild

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                read_messages=False
            ),

            interaction.user: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True
            )
        }

        channel = await guild.create_text_channel(
            name=f"brainrot-{interaction.user.name}",
            overwrites=overwrites
        )

        await interaction.response.send_message(
            f"✅ Ticket opened: {channel.mention}",
            ephemeral=True
        )

        staff_role = guild.get_role(STAFF_ROLE_ID)

        if staff_role:

            await channel.send(
                f"{staff_role.mention} 🔔 New Brainrot Ticket"
            )

        embed = discord.Embed(
            color=0x2b2d31
        )

        embed.add_field(
            name="<:brainrot:1507881329499570246> • Brainrot Payment Ticket •",
            value=(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Please wait for a staff member.\n"
                "A staff member will assist you shortly."
            ),
            inline=False
        )

        embed.set_footer(
            text="Do not spam ping staff."
        )

        await channel.send(
            embed=embed,
            view=CloseTicketView()
        )

# =========================================================
# PANEL COMMAND
# =========================================================

@bot.tree.command(
    name="panel",
    description="Deploy payment panel"
)
async def panel(interaction: discord.Interaction):

    # LTC PANEL

    ltc_embed = discord.Embed(
        color=0x2b2d31
    )

    ltc_embed.add_field(
        name="<:ltc:1507880812643614972> • Pay with Litecoin •",
        value=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Secure automatic crypto payments.\n\n"
            "• Automatic blockchain verification\n"
            "• Instant Buyer role delivery\n"
            "• Secure escrow checkout"
        ),
        inline=False
    )

    # BRAINROT PANEL

    brain_embed = discord.Embed(
        color=0x2b2d31
    )

    brain_embed.add_field(
        name="<:brainrot:1507881329499570246> • Pay with Brainrots •",
        value=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Open a Brainrot payment/support ticket.\n\n"
            "• Private support ticket\n"
            "• Staff assistance\n"
            "• Fast response"
        ),
        inline=False
    )

    await interaction.channel.send(
        embed=ltc_embed,
        view=LitecoinPanel()
    )

    await interaction.channel.send(
        embed=brain_embed,
        view=BrainrotPanel()
    )

    await interaction.response.send_message(
        "✅ Panels deployed.",
        ephemeral=True
    )

# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print(f"Logged in as {bot.user}")

# =========================================================
# RUN
# =========================================================

bot.run(TOKEN)