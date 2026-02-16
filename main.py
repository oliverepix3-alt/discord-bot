import discord
from discord.ext import commands
import asyncio
import re
import os
from datetime import timedelta

# Bot setup with all necessary intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Store pending violations {message_id: {user, channel, violation_type, timestamp}}
pending_violations = {}

# Detection patterns
SLUR_PATTERNS = [
    r'\bn[i1!]gg[e3]r',
    r'\bf[a4]gg[o0]t',
    r'\br[e3]t[a4]rd',
    r'\bc[u]nt',
    r'\btr[a4]nny',
]

SEXUAL_PATTERNS = [
    r'\bsex',
    r'\bporn',
    r'\bxxx',
    r'\bhentai',
    r'\bnude',
    r'\bdick',
    r'\bpussy',
    r'\bc[o0]ck',
    r'\bf[u]ck',
]

NSFW_LINK_PATTERNS = [
    r'pornhub\.com',
    r'xvideos\.com',
    r'xhamster\.com',
    r'onlyfans\.com',
    r'xxx',
]

def check_slurs(content):
    """Check for slurs and hate speech"""
    content_lower = content.lower()
    for pattern in SLUR_PATTERNS:
        if re.search(pattern, content_lower, re.IGNORECASE):
            return True
    return False

def check_sexual_content(content):
    """Check for sexual content"""
    content_lower = content.lower()
    for pattern in SEXUAL_PATTERNS:
        if re.search(pattern, content_lower, re.IGNORECASE):
            return True
    return False

def check_nsfw_links(content):
    """Check for NSFW links"""
    for pattern in NSFW_LINK_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return True
    return False

def check_spam(message, recent_messages):
    """Check for spam/flooding (same message repeated)"""
    if len(recent_messages) >= 5:
        same_content_count = sum(1 for msg in recent_messages if msg.content == message.content)
        if same_content_count >= 3:
            return True
    return False

user_messages = {}

@bot.event
async def on_ready():
    print(f'{bot.user} is now online and monitoring!')
    print(f'Bot is in {len(bot.guilds)} server(s)')

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    
    if message.channel.name == 'logs' and message.author.guild_permissions.administrator:
        if message.reference and message.reference.message_id in pending_violations:
            violation_id = message.reference.message_id
            violation_data = pending_violations[violation_id]
            
            log_message = violation_data['log_message']
            embed = log_message.embeds[0]
            embed.color = discord.Color.green()
            embed.set_footer(text=f"✅ Handled by {message.author.name}")
            await log_message.edit(embed=embed)
            
            del pending_violations[violation_id]
            await message.add_reaction('✅')
            return
    
    if message.author.guild_permissions.administrator:
        await bot.process_commands(message)
        return
    
    if message.author.id not in user_messages:
        user_messages[message.author.id] = []
    user_messages[message.author.id].append(message)
    user_messages[message.author.id] = user_messages[message.author.id][-10:]
    
    violation_types = []
    
    if check_slurs(message.content):
        violation_types.append("Slurs/Hate Speech")
    
    if check_sexual_content(message.content):
        violation_types.append("Sexual Content")
    
    if check_nsfw_links(message.content):
        violation_types.append("NSFW Links")
    
    if check_spam(message, user_messages[message.author.id]):
        violation_types.append("Spam/Flooding")
    
    if violation_types:
        await handle_violation(message, violation_types)
    
    await bot.process_commands(message)

async def handle_violation(message, violation_types):
    logs_channel = discord.utils.get(message.guild.text_channels, name='logs')
    
    if not logs_channel:
        print(f"Warning: #logs channel not found in {message.guild.name}")
        return
    
    embed = discord.Embed(
        title="⚠️ Content Violation Detected",
        color=discord.Color.red(),
        timestamp=message.created_at
    )
    
    embed.add_field(name="User", value=f"{message.author.mention} ({message.author})", inline=False)
    embed.add_field(name="Channel", value=message.channel.mention, inline=False)
    embed.add_field(name="Violation Type(s)", value=", ".join(violation_types), inline=False)
    embed.add_field(name="Message Content", value=message.content[:1024] if message.content else "*No text content*", inline=False)
    embed.add_field(name="Message Link", value=f"[Jump to Message]({message.jump_url})", inline=False)
    embed.set_footer(text="⏰ User will be timed out in 5 minutes if no admin responds")
    
    log_message = await logs_channel.send(embed=embed)
    
    pending_violations[log_message.id] = {
        'user': message.author,
        'channel': message.channel,
        'violation_types': violation_types,
        'original_message': message,
        'log_message': log_message
    }
    
    await asyncio.sleep(300)
    
    if log_message.id in pending_violations:
        violation_data = pending_violations[log_message.id]
        
        try:
            await violation_data['user'].timeout(timedelta(hours=1), reason=f"Auto-timeout: {', '.join(violation_types)}")
            
            embed = log_message.embeds[0]
            embed.color = discord.Color.dark_red()
            embed.set_footer(text="🔇 User has been automatically timed out for 1 hour (no admin response)")
            await log_message.edit(embed=embed)
            
            await logs_channel.send(f"🔇 {violation_data['user'].mention} has been timed out for 1 hour due to: {', '.join(violation_types)}")
            
        except discord.Forbidden:
            await logs_channel.send(f"⚠️ Failed to timeout {violation_data['user'].mention} - insufficient permissions")
        except Exception as e:
            await logs_channel.send(f"⚠️ Error timing out user: {str(e)}")
        
        del pending_violations[log_message.id]

@bot.command(name='modstats')
@commands.has_permissions(administrator=True)
async def mod_stats(ctx):
    embed = discord.Embed(
        title="📊 Moderation Statistics",
        color=discord.Color.blue()
    )
    embed.add_field(name="Pending Violations", value=len(pending_violations), inline=True)
    embed.add_field(name="Bot Status", value="✅ Active", inline=True)
    await ctx.send(embed=embed)

@bot.command(name='clearviolation')
@commands.has_permissions(administrator=True)
async def clear_violation(ctx, message_id: int):
    if message_id in pending_violations:
        del pending_violations[message_id]
        await ctx.send(f"✅ Cleared pending violation (Message ID: {message_id})")
    else:
        await ctx.send(f"❌ No pending violation found with that message ID")

bot.run(os.getenv('MTQ3MjgwMDMxMDUzNDczMzkwNQ.G2U1-M.KYUDEuk5896WtrISfmewBQD-FBYFrPJCRL8x-I'))
