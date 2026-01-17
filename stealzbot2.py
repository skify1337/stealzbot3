import discord
from discord.ext import commands
from discord import app_commands, ui, ButtonStyle
import asyncio
import uuid
import os
import json
from dotenv import load_dotenv
from typing import Optional, Dict, List, Set
from datetime import datetime

# ===================== ЗАГРУЗКА ТОКЕНА ИЗ .env =====================
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

if not TOKEN:
    print("❌ ОШИБКА: DISCORD_TOKEN не найден в .env файле!")
    exit(1)

# ===================== НАСТРОЙКИ =====================
HIGH_ROLES = [1174860973522288780, 1089620679021842605, 1174878142259793962, 1245089436723581042]  # Роли админов
TIER_ROLES = {
    1: 1458095828722909224,  # Тир 1
    2: 1458095871810867250,  # Тир 2
    3: 1458095875460173938   # Тир 3
}
ALLOWED_CHANNEL = 1451552947300204594  # Канал для команд
STATS_CHANNEL = 1174883465066451016  # Канал для статистики
MAX_PARTICIPANTS_PER_VZP = 100
MAX_ACTIVE_VZP = 10
MIN_PARTICIPANTS_PER_VZP = 1

# ===================== PERSISTENT VIEWS =====================
class VZPView(ui.View):
    def __init__(self, vzp_id: str):
        super().__init__(timeout=None)
        self.vzp_id = vzp_id
        
        self.button = ui.Button(
            style=ButtonStyle.green,
            label="ПОДАТЬ ПЛЮС",
            custom_id=f"vzp_button_{vzp_id}",
            emoji="➕"
        )
        self.button.callback = self.button_callback
        self.add_item(self.button)
    
    async def button_callback(self, interaction: discord.Interaction):
        await handle_vzp_button(interaction, self.vzp_id)

# ===================== ХРАНИЛИЩА ДАННЫХ =====================
class VZPData:
    def __init__(self, data: dict):
        self.time: str = data.get('time', '')
        self.members: int = data.get('members', 0)
        self.enemy: str = data.get('enemy', '')
        self.attack_def: str = data.get('attack_def', '')
        self.attack_def_name: str = data.get('attack_def_name', '')
        self.conditions: List[str] = data.get('conditions', [])
        self.conditions_display: List[str] = data.get('conditions_display', [])
        self.calibers: List[str] = data.get('calibers', [])
        self.caliber_names: List[str] = data.get('caliber_names', [])
        self.message_id: int = data.get('message_id', 0)
        self.channel_id: int = data.get('channel_id', 0)
        self.category_id: Optional[int] = data.get('category_id')
        self.plus_users: Dict[int, int] = data.get('plus_users', {})
        self.status: str = data.get('status', 'OPEN')
        self.created_at: str = data.get('created_at', datetime.now().isoformat())
        self.result: Optional[str] = data.get('result')
        self.amount: Optional[int] = data.get('amount')

active_vzp: Dict[str, VZPData] = {}
closed_vzp: Dict[str, dict] = {}
swap_history: Dict[str, Dict[int, int]] = {}
vzp_views: Dict[str, VZPView] = {}
position_assignments: Dict[str, Dict[int, Optional[discord.Member]]] = {}
position_messages: Dict[str, Dict[str, int]] = {}
active_position_calls: Dict[int, Dict] = {}
user_notification_messages: Dict[str, Dict[int, int]] = {}

DATA_FILE = "vzp_data.json"
SWAP_FILE = "swap_data.json"
POSITIONS_FILE = "positions_data.json"
POSITIONS_CALLS_FILE = "positions_calls.json"
NOTIFICATION_FILE = "notification_data.json"

def save_data():
    try:
        vzp_data = {}
        for vzp_id, vzp in active_vzp.items():
            vzp_data[vzp_id] = {
                'time': vzp.time,
                'members': vzp.members,
                'enemy': vzp.enemy,
                'attack_def': vzp.attack_def,
                'attack_def_name': vzp.attack_def_name,
                'conditions': vzp.conditions,
                'conditions_display': vzp.conditions_display,
                'calibers': vzp.calibers,
                'caliber_names': vzp.caliber_names,
                'message_id': vzp.message_id,
                'channel_id': vzp.channel_id,
                'category_id': vzp.category_id,
                'plus_users': vzp.plus_users,
                'status': vzp.status,
                'created_at': vzp.created_at,
                'result': vzp.result,
                'amount': vzp.amount
            }
        
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'active': vzp_data,
                'closed': closed_vzp
            }, f, ensure_ascii=False, indent=2)
        
        with open(SWAP_FILE, 'w', encoding='utf-8') as f:
            json.dump(swap_history, f, ensure_ascii=False, indent=2)
        
        positions_to_save = {}
        for vzp_id, positions in position_assignments.items():
            positions_to_save[vzp_id] = {
                pos: member.id if member else None 
                for pos, member in positions.items()
            }
        
        with open(POSITIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'assignments': positions_to_save,
                'messages': position_messages
            }, f, ensure_ascii=False, indent=2)
        
        calls_to_save = {}
        for channel_id, call_data in active_position_calls.items():
            calls_to_save[channel_id] = {
                "pos_id": call_data.get("pos_id"),
                "vzp_id": call_data.get("vzp_id"),
                "created_by": call_data.get("created_by"),
                "created_at": call_data.get("created_at")
            }
        
        with open(POSITIONS_CALLS_FILE, 'w', encoding='utf-8') as f:
            json.dump(calls_to_save, f, ensure_ascii=False, indent=2)
        
        with open(NOTIFICATION_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_notification_messages, f, ensure_ascii=False, indent=2)
        
        print(f"💾 Данные сохранены: {len(active_vzp)} активных VZP, {len(active_position_calls)} активных распределений")
    except Exception as e:
        print(f"❌ Ошибка сохранения данных: {e}")

def load_data():
    global active_vzp, closed_vzp, swap_history, position_assignments, position_messages, active_position_calls, user_notification_messages
    
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                active_data = data.get('active', {})
                for vzp_id, vzp_data in active_data.items():
                    if 'plus_users' in vzp_data:
                        vzp_data['plus_users'] = {int(k): int(v) for k, v in vzp_data['plus_users'].items()}
                    
                    active_vzp[vzp_id] = VZPData(vzp_data)
                
                closed_vzp = data.get('closed', {})
        
        if os.path.exists(SWAP_FILE):
            with open(SWAP_FILE, 'r', encoding='utf-8') as f:
                swap_data = json.load(f)
                swap_history = {k: {int(k2): int(v2) for k2, v2 in v.items()} for k, v in swap_data.items()}
        
        if os.path.exists(POSITIONS_FILE):
            with open(POSITIONS_FILE, 'r', encoding='utf-8') as f:
                positions_data = json.load(f)
                
                assignments_data = positions_data.get('assignments', {})
                for vzp_id, positions in assignments_data.items():
                    position_assignments[vzp_id] = {}
                    for pos_str, member_id in positions.items():
                        pos = int(pos_str)
                        if member_id:
                            member = None
                            for guild in bot.guilds:
                                member = guild.get_member(member_id)
                                if member:
                                    break
                            position_assignments[vzp_id][pos] = member
                        else:
                            position_assignments[vzp_id][pos] = None
                
                position_messages = positions_data.get('messages', {})
        
        if os.path.exists(POSITIONS_CALLS_FILE):
            with open(POSITIONS_CALLS_FILE, 'r', encoding='utf-8') as f:
                calls_data = json.load(f)
                active_position_calls = {int(k): v for k, v in calls_data.items()}
        
        if os.path.exists(NOTIFICATION_FILE):
            with open(NOTIFICATION_FILE, 'r', encoding='utf-8') as f:
                user_notification_messages = json.load(f)
        
        print(f"📂 Данные загружены: {len(active_vzp)} активных VZP, {len(active_position_calls)} активных распределений")
    except Exception as e:
        print(f"❌ Ошибка загрузки данных: {e}")
        active_vzp = {}
        closed_vzp = {}
        swap_history = {}
        position_assignments = {}
        position_messages = {}
        active_position_calls = {}
        user_notification_messages = {}

# ===================== НАСТРОЙКА БОТА =====================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class VZPBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
    
    async def setup_hook(self):
        load_data()
        
        for vzp_id, vzp_data in active_vzp.items():
            if vzp_data.status == 'OPEN':
                view = VZPView(vzp_id)
                self.add_view(view)
        
        try:
            synced = await self.tree.sync()
            print(f"✅ Синхронизировано {len(synced)} команд")
        except Exception as e:
            print(f"❌ Ошибка синхронизации: {e}")

bot = VZPBot()

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
async def is_allowed_channel(interaction: discord.Interaction) -> bool:
    return interaction.channel_id == ALLOWED_CHANNEL

async def has_high_role(interaction: discord.Interaction) -> bool:
    return any(role.id in HIGH_ROLES for role in interaction.user.roles)

async def get_user_tier(user: discord.Member) -> Optional[int]:
    for tier_num, role_id in TIER_ROLES.items():
        if any(role.id == role_id for role in user.roles):
            return tier_num
    return None

async def create_vzp_embed(vzp_id: str, vzp_data: VZPData) -> discord.Embed:
    status_colors = {
        'OPEN': discord.Color.green(),
        'LIST IN PROCESS': discord.Color.gold(),
        'VZP IN PROCESS': discord.Color.blue(),
        'CLOSED': discord.Color.red()
    }
    color = status_colors.get(vzp_data.status, discord.Color.green())
    
    attack_def_display = vzp_data.attack_def_name.split(' ')[1]
    
    description = f"**{attack_def_display} {len(vzp_data.plus_users)}/{vzp_data.members} {vzp_data.time}**\n"
    description += f"\n**{', '.join(vzp_data.conditions_display)}**\n"
    description += f"**{vzp_data.caliber_names[0]} + {vzp_data.caliber_names[1]} + {vzp_data.caliber_names[2]}**"
    
    embed = discord.Embed(description=description, color=color)
    
    tier_lists = {1: [], 2: [], 3: []}
    for user_id, tier in vzp_data.plus_users.items():
        tier_lists[tier].append(user_id)
    
    for tier_num in [1, 2, 3]:
        members_list = []
        for user_id in tier_lists[tier_num]:
            member = bot.get_guild(interaction.guild.id).get_member(user_id) if 'interaction' in locals() else None
            if member:
                members_list.append(f"• {member.mention}")
            else:
                members_list.append(f"• <@{user_id}>")
        
        tier_name = {1: "TIER 1", 2: "TIER 2", 3: "TIER 3"}[tier_num]
        embed.add_field(
            name=f"**{tier_name}** ({len(tier_lists[tier_num])})",
            value="\n".join(members_list) if members_list else "—",
            inline=False
        )
    
    vzp_swaps = swap_history.get(vzp_id, {})
    if vzp_swaps:
        swap_list = []
        for old_user_id, new_user_id in vzp_swaps.items():
            old_member = bot.get_guild(interaction.guild.id).get_member(old_user_id) if 'interaction' in locals() else None
            new_member = bot.get_guild(interaction.guild.id).get_member(new_user_id) if 'interaction' in locals() else None
            
            old_name = old_member.mention if old_member else f"<@{old_user_id}>"
            new_name = new_member.mention if new_member else f"<@{new_user_id}>"
            swap_list.append(f"• {new_name} → {old_name}")
        
        if swap_list:
            embed.add_field(name="**SWAP**", value="\n".join(swap_list), inline=False)
    
    embed.add_field(name="**STATUS**", value=f"```{vzp_data.status}```", inline=False)
    embed.add_field(name="**ID**", value=f"```{vzp_id}```", inline=False)
    
    return embed

async def update_vzp_message(vzp_id: str):
    if vzp_id not in active_vzp:
        return
    
    vzp_data = active_vzp[vzp_id]
    
    try:
        channel = bot.get_channel(vzp_data.channel_id)
        if not channel:
            return
        
        message = await channel.fetch_message(vzp_data.message_id)
        embed = await create_vzp_embed(vzp_id, vzp_data)
        
        view = None
        if vzp_data.status == 'OPEN':
            view = VZPView(vzp_id)
        
        await message.edit(embed=embed, view=view)
    
    except discord.NotFound:
        print(f"Сообщение VZP {vzp_id} не найдено")
    except Exception as e:
        print(f"Ошибка обновления VZP {vzp_id}: {e}")

async def update_position_message(pos_id: str):
    if pos_id not in position_messages:
        return
    
    msg_info = position_messages[pos_id]
    channel = bot.get_channel(msg_info["channel_id"])
    if not channel:
        return
    
    try:
        message = await channel.fetch_message(msg_info["message_id"])
        positions = position_assignments.get(pos_id, {})
        
        lines = []
        for pos in sorted(positions.keys()):
            member = positions[pos]
            if member:
                lines.append(f"{pos} - {member.mention}")
            else:
                lines.append(f"{pos} - ...")
        
        total = len(positions)
        occupied = sum(1 for member in positions.values() if member)
        free = total - occupied
        
        embed = discord.Embed(
            title="🎯 РАСПРЕДЕЛЕНИЕ ПОЗИЦИЙ",
            description="\n".join(lines),
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📊 СТАТИСТИКА",
            value=f"**Занято:** {occupied}/{total}\n"
                  f"**Свободно:** {free}",
            inline=True
        )
        
        if pos_id.startswith("POS_"):
            pass
        elif pos_id in active_vzp:
            vzp_data = active_vzp[pos_id]
            embed.title = f"🎯 РАСПРЕДЕЛЕНИЕ ПОЗИЦИЙ VZP {pos_id}"
            embed.add_field(
                name="📅 ИНФОРМАЦИЯ О VZP",
                value=f"**Время:** {vzp_data.time}\n"
                      f"**Статус:** {vzp_data.status}\n"
                      f"**Участников VZP:** {len(vzp_data.plus_users)}/{vzp_data.members}",
                inline=False
            )
        
        embed.add_field(
            name="📝 КАК ЗАПИСАТЬСЯ",
            value="**Отправьте номер позиции в этот канал**\n"
                  "**Чтобы освободить позицию, отправьте `отмена`**",
            inline=False
        )
        
        embed.set_footer(text="Автоматическое обновление")
        
        await message.edit(embed=embed)
        save_data()
    except Exception as e:
        print(f"Ошибка обновления позиций: {e}")

async def send_position_notification(channel: discord.TextChannel, message_id: int, user_id: int, content: str):
    """Отправляет уведомление о записи/отмене в канал, но только для указанного пользователя"""
    try:
        # Проверяем, есть ли уже сообщение для этого пользователя
        if str(message_id) in user_notification_messages:
            if user_id in user_notification_messages[str(message_id)]:
                try:
                    old_msg_id = user_notification_messages[str(message_id)][user_id]
                    old_msg = await channel.fetch_message(old_msg_id)
                    await old_msg.delete()
                except:
                    pass
        
        # Отправляем новое сообщение
        msg = await channel.send(content)
        
        # Сохраняем ID сообщения
        if str(message_id) not in user_notification_messages:
            user_notification_messages[str(message_id)] = {}
        user_notification_messages[str(message_id)][user_id] = msg.id
        
        # Удаляем сообщение через 5 секунд
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except:
            pass
        
        # Удаляем из сохраненных данных
        if str(message_id) in user_notification_messages and user_id in user_notification_messages[str(message_id)]:
            del user_notification_messages[str(message_id)][user_id]
            if not user_notification_messages[str(message_id)]:
                del user_notification_messages[str(message_id)]
        
        save_data()
    except Exception as e:
        print(f"Ошибка отправки уведомления: {e}")

async def handle_vzp_button(interaction: discord.Interaction, vzp_id: str):
    if vzp_id not in active_vzp:
        await interaction.response.send_message(
            "Эта VZP больше не активна!",
            ephemeral=True
        )
        return
    
    vzp_data = active_vzp[vzp_id]
    user = interaction.user
    
    tier = await get_user_tier(user)
    if not tier:
        await interaction.response.send_message(
            "У вас нет необходимой роли для участия в VZP!",
            ephemeral=True
        )
        return
    
    if vzp_data.status != 'OPEN':
        await interaction.response.send_message(
            f"Набор на эту VZP закрыт! Текущий статус: {vzp_data.status}",
            ephemeral=True
        )
        return
    
    vzp_swaps = swap_history.get(vzp_id, {})
    if user.id in vzp_swaps.values():
        await interaction.response.send_message(
            "Вы уже в списке замен!",
            ephemeral=True
        )
        return
    
    if len(vzp_data.plus_users) >= MAX_PARTICIPANTS_PER_VZP:
        await interaction.response.send_message(
            f"Достигнут максимальный лимит участников ({MAX_PARTICIPANTS_PER_VZP})!",
            ephemeral=True
        )
        return
    
    is_in_list = user.id in vzp_data.plus_users
    
    if is_in_list:
        del vzp_data.plus_users[user.id]
    else:
        vzp_data.plus_users[user.id] = tier

    await update_vzp_message(vzp_id)
    save_data()
    
    if is_in_list:
        await interaction.response.send_message("Вы удалились из списка VZP!", ephemeral=True)
    else:
        await interaction.response.send_message("Вы успешно записались на VZP!", ephemeral=True)

async def notify_users_ls(vzp_id: str, title: str, message: str, guild: discord.Guild, user_ids: Set[int] = None) -> int:
    if vzp_id not in active_vzp:
        return 0
    
    vzp_data = active_vzp[vzp_id]
    notified = 0
    
    target_ids = user_ids if user_ids else set(vzp_data.plus_users.keys())
    
    for user_id in target_ids:
        member = guild.get_member(user_id)
        if member:
            try:
                embed = discord.Embed(title=title, description=message, color=discord.Color.blue())
                embed.add_field(name="VZP ID", value=vzp_id, inline=False)
                embed.add_field(name="Время", value=vzp_data.time, inline=True)
                embed.set_footer(text="VZP Manager")
                
                await member.send(embed=embed)
                notified += 1
            except:
                pass
            
            await asyncio.sleep(0.1)
    
    return notified

async def post_vzp_result(vzp_id: str, result: str, amount: int, guild: discord.Guild):
    if vzp_id not in active_vzp:
        return
    
    vzp_data = active_vzp[vzp_id]
    stats_channel = guild.get_channel(STATS_CHANNEL)
    
    if not stats_channel or not isinstance(stats_channel, discord.TextChannel):
        print(f"❌ Канал статистики {STATS_CHANNEL} не найден!")
        return
    
    all_players = set(vzp_data.plus_users.keys())
    
    vzp_swaps = swap_history.get(vzp_id, {})
    for new_user_id in vzp_swaps.values():
        all_players.add(new_user_id)
    
    players_list = []
    for i, user_id in enumerate(sorted(all_players), 1):
        member = guild.get_member(user_id)
        if member:
            players_list.append(f"{i} - {member.mention}")
        else:
            players_list.append(f"{i} - <@{user_id}>")
    
    result_display = result.upper()
    result_info = {
        "WIN": {"color": discord.Color.green(), "title": "ПОБЕДА"},
        "LOSE": {"color": discord.Color.red(), "title": "ПОРАЖЕНИЕ"},
    }.get(result_display, {"color": discord.Color.blue(), "title": "РЕЗУЛЬТАТ"})
    
    embed = discord.Embed(
        title=f"VZP РЕЗУЛЬТАТ: {result_info['title']}",
        color=result_info['color'],
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="  МАТЧ  ",
        value=f"**{vzp_data.time}** vs **{vzp_data.enemy}**\n"
              f"Участников: **{len(all_players)}** из **{vzp_data.members}**\n"
              f"**КОЛИЧЕСТВО ТОЧЕК - {amount}**",
        inline=False
    )
    
    attack_def_display = vzp_data.attack_def_name.split(' ')[1]
    embed.add_field(
        name="УСЛОВИЯ",
        value=f"Тип: **{attack_def_display}**\n"
              f"Условия: **{', '.join(vzp_data.conditions_display)}**\n"
              f"Калибры: **{vzp_data.caliber_names[0]} + {vzp_data.caliber_names[1]} + {vzp_data.caliber_names[2]}**",
        inline=False
    )
    
    if players_list:
        players_text = "\n".join(players_list)
        
        if len(players_text) > 1024:
            chunk_size = 20
            chunks = [players_list[i:i + chunk_size] for i in range(0, len(players_list), chunk_size)]
            
            for i, chunk in enumerate(chunks, 1):
                chunk_text = "\n".join(chunk)
                embed.add_field(
                    name=f"👥 УЧАСТНИКИ (часть {i})",
                    value=chunk_text,
                    inline=False
                )
        else:
            embed.add_field(
                name="👥 УЧАСТНИКИ",
                value=players_text,
                inline=False
            )
    
    if vzp_swaps:
        swap_info = []
        for old_user_id, new_user_id in vzp_swaps.items():
            old_member = guild.get_member(old_user_id)
            new_member = guild.get_member(new_user_id)
            
            old_name = old_member.display_name if old_member else f"ID:{old_user_id}"
            new_name = new_member.display_name if new_member else f"ID:{new_user_id}"
            swap_info.append(f"• {new_name} заменил {old_name}")
        
        if swap_info:
            embed.add_field(
                name="🔄 ЗАМЕНЫ",
                value="\n".join(swap_info),
                inline=False
            )
    
    embed.set_footer(text=f"VZP ID: {vzp_id} | {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    
    await stats_channel.send(embed=embed)
    
    return len(all_players)

# ===================== ОБРАБОТЧИК СООБЩЕНИЙ =====================
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    if message.channel.id not in active_position_calls:
        return
    
    pos_info = active_position_calls[message.channel.id]
    pos_id = pos_info["pos_id"]
    positions = position_assignments.get(pos_id, {})
    msg_info = position_messages.get(pos_id, {})
    
    if not msg_info:
        return
    
    content = message.content.lower().strip()
    
    if content in ["отмена", "cancel", "удалить", "delete", "освободить"]:
        user_positions = []
        for pos, member in positions.items():
            if member and member.id == message.author.id:
                user_positions.append(pos)
        
        if not user_positions:
            # Используем новую функцию для отправки уведомления
            await send_position_notification(
                message.channel,
                msg_info["message_id"],
                message.author.id,
                f"{message.author.mention} ❌ Вы не занимаете ни одной позиции!"
            )
            try:
                await message.delete()
            except:
                pass
            return
        
        for pos in user_positions:
            positions[pos] = None
        
        await update_position_message(pos_id)
        
        if len(user_positions) == 1:
            reply = f"{message.author.mention} ✅ Вы освободили позицию {user_positions[0]}!"
        else:
            reply = f"{message.author.mention} ✅ Вы освободили позиции: {', '.join(map(str, user_positions))}!"
        
        await send_position_notification(
            message.channel,
            msg_info["message_id"],
            message.author.id,
            reply
        )
        try:
            await message.delete()
        except:
            pass
        return
    
    try:
        requested_pos = int(content)
    except ValueError:
        return
    
    if requested_pos not in positions:
        await send_position_notification(
            message.channel,
            msg_info["message_id"],
            message.author.id,
            f"{message.author.mention} ❌ Позиция {requested_pos} не существует! Доступные позиции: 1-{len(positions)}"
        )
        try:
            await message.delete()
        except:
            pass
        return
    
    current_holder = positions[requested_pos]
    if current_holder:
        if current_holder.id == message.author.id:
            await send_position_notification(
                message.channel,
                msg_info["message_id"],
                message.author.id,
                f"{message.author.mention} ❌ Вы уже занимаете позицию {requested_pos}! Используйте `отмена` чтобы освободить."
            )
        else:
            await send_position_notification(
                message.channel,
                msg_info["message_id"],
                message.author.id,
                f"{message.author.mention} ❌ Позиция {requested_pos} уже занята {current_holder.mention}!"
            )
        try:
            await message.delete()
        except:
            pass
        return
    
    # Проверяем, не занимает ли пользователь уже другую позицию
    user_already_has_position = False
    user_current_position = None
    for pos, member in positions.items():
        if member and member.id == message.author.id:
            user_already_has_position = True
            user_current_position = pos
            break
    
    if user_already_has_position:
        await send_position_notification(
            message.channel,
            msg_info["message_id"],
            message.author.id,
            f"{message.author.mention} ❌ Вы уже занимаете позицию {user_current_position}! Используйте `отмена` чтобы освободить её, прежде чем занять новую."
        )
        try:
            await message.delete()
        except:
            pass
        return
    
    positions[requested_pos] = message.author
    await update_position_message(pos_id)
    
    await send_position_notification(
        message.channel,
        msg_info["message_id"],
        message.author.id,
        f"{message.author.mention} ✅ Вы успешно заняли позицию {requested_pos}!"
    )
    try:
        await message.delete()
    except:
        pass

# ===================== КОМАНДЫ =====================

@bot.tree.command(name="vzp_start", description="Создать новую VZP с выбором условий")
@app_commands.describe(
    time="Время VZP (например: 20:00)",
    members="Количество участников",
    attack_def="Выберите АТАКУ или ОБОРОНУ",
    condition1="Выберите первое условие забива",
    caliber1="Выберите первый калибр",
    caliber2="Выберите второй калибр",
    caliber3="Выберите третий калибр",
    condition2="Выберите второе условие забива (не обязательно)",
    condition3="Выберите третье условие забива (не обязательно)"
)
@app_commands.choices(
    attack_def=[
        app_commands.Choice(name=" АТАКА", value="ATT"),
        app_commands.Choice(name=" ДЕФ", value="DEF")
    ],
    condition1=[
        app_commands.Choice(name="Алкоголь/анальгетик", value="alcohol"),
        app_commands.Choice(name="Косяки/SPANK", value="joints"),
        app_commands.Choice(name="Аптечки", value="medkits"),
        app_commands.Choice(name="Броня", value="armor")
    ],
    condition2=[
        app_commands.Choice(name="Алкоголь/анальгетик", value="alcohol"),
        app_commands.Choice(name="Косяки/SPANK", value="joints"),
        app_commands.Choice(name="Аптечки", value="medkits"),
        app_commands.Choice(name="Броня", value="armor"),
    ],
    condition3=[
        app_commands.Choice(name="Алкоголь/анальгетик", value="alcohol"),
        app_commands.Choice(name="Косяки/SPANK", value="joints"),
        app_commands.Choice(name="Аптечки", value="medkits"),
        app_commands.Choice(name="Броня", value="armor"),
    ],
    caliber1=[
        app_commands.Choice(name="5.56 mm", value="5.56"),
        app_commands.Choice(name="7.62 mm", value="7.62"),
        app_commands.Choice(name="11.43 mm", value="11.43"),
        app_commands.Choice(name="9 mm", value="9"),
        app_commands.Choice(name="12 mm", value="12")
    ],
    caliber2=[
        app_commands.Choice(name="5.56 mm", value="5.56"),
        app_commands.Choice(name="7.62 mm", value="7.62"),
        app_commands.Choice(name="11.43 mm", value="11.43"),
        app_commands.Choice(name="9 mm", value="9"),
        app_commands.Choice(name="12 mm", value="12")
    ],
    caliber3=[
        app_commands.Choice(name="5.56 mm", value="5.56"),
        app_commands.Choice(name="7.62 mm", value="7.62"),
        app_commands.Choice(name="11.43 mm", value="11.43"),
        app_commands.Choice(name="9 mm", value="9"),
        app_commands.Choice(name="12 mm", value="12")
    ]
)
async def vzp_start(
    interaction: discord.Interaction,
    time: str,
    members: int,
    attack_def: app_commands.Choice[str],
    condition1: app_commands.Choice[str],
    caliber1: app_commands.Choice[str],
    caliber2: app_commands.Choice[str],
    caliber3: app_commands.Choice[str],
    condition2: app_commands.Choice[str] = None,
    condition3: app_commands.Choice[str] = None
):
    if not await is_allowed_channel(interaction):
        await interaction.response.send_message(
            f"❌ Эту команду можно использовать только в канале <#{ALLOWED_CHANNEL}>!",
            ephemeral=True
        )
        return
    
    if not await has_high_role(interaction):
        await interaction.response.send_message(
            "❌ У вас нет прав для создания VZP!",
            ephemeral=True
        )
        return
    
    if len(active_vzp) >= MAX_ACTIVE_VZP:
        await interaction.response.send_message(
            f"❌ Достигнут лимит активных VZP ({MAX_ACTIVE_VZP})! "
            f"Закройте некоторые VZP командой `/close_vzp`",
            ephemeral=True
        )
        return
    
    if members > MAX_PARTICIPANTS_PER_VZP:
        await interaction.response.send_message(
            f"❌ Максимальное количество участников: {MAX_PARTICIPANTS_PER_VZP}",
            ephemeral=True
        )
        return
    
    if members < MIN_PARTICIPANTS_PER_VZP:
        await interaction.response.send_message(
            f"❌ Минимальное количество участников: {MIN_PARTICIPANTS_PER_VZP}",
            ephemeral=True
        )
        return
    
    calibers = [caliber1.value, caliber2.value, caliber3.value]
    if len(set(calibers)) < 3:
        await interaction.response.send_message(
            "❌ Выберите три РАЗНЫХ калибра!",
            ephemeral=True
        )
        return
    
    vzp_id = str(uuid.uuid4())[:8]
    
    condition_names = {
        "alcohol": "Алкоголь/анальгетик",
        "joints": "Косяки/SPANK",
        "medkits": "Аптечки",
        "armor": "Броня"
    }
    
    conditions_display = [condition_names.get(condition1.value, condition1.value)]
    conditions_values = [condition1.value]
    
    if condition2 and condition2.value not in conditions_values:
        conditions_display.append(condition_names.get(condition2.value, condition2.value))
        conditions_values.append(condition2.value)
    
    if condition3 and condition3.value not in conditions_values:
        conditions_display.append(condition_names.get(condition3.value, condition3.value))
        conditions_values.append(condition3.value)
    
    attack_def_display = attack_def.name.split(' ')[1]
    
    description = f"**{attack_def_display} 0/{members} {time}**\n"
    description += f"\n**{', '.join(conditions_display)}**\n"
    description += f"**{caliber1.name} + {caliber2.name} + {caliber3.name}**"
    
    embed = discord.Embed(description=description, color=discord.Color.green())
    
    for tier_num in [1, 2, 3]:
        embed.add_field(name=f"**TIER {tier_num}** (0)", value="—", inline=False)
    
    embed.add_field(name="**STATUS**", value=f"```OPEN```", inline=False)
    embed.add_field(name="**ID**", value=f"```{vzp_id}```", inline=False)
    
    view = VZPView(vzp_id)
    
    await interaction.response.send_message(embed=embed, view=view)
    message = await interaction.original_response()
    
    vzp_data = VZPData({
        'time': time,
        'members': members,
        'enemy': '',
        'attack_def': attack_def.value,
        'attack_def_name': attack_def.name,
        'conditions': conditions_values,
        'conditions_display': conditions_display,
        'calibers': calibers,
        'caliber_names': [caliber1.name, caliber2.name, caliber3.name],
        'message_id': message.id,
        'channel_id': interaction.channel_id,
        'plus_users': {},
        'status': 'OPEN',
        'created_at': datetime.now().isoformat(),
        'result': None,
        'amount': None
    })
    
    active_vzp[vzp_id] = vzp_data
    swap_history[vzp_id] = {}
    save_data()
    
    try:
        await asyncio.sleep(1)
        for i in range(5):
            await interaction.channel.send("@everyone")
            await asyncio.sleep(0.2)
        print(f"✅ Автопинг отправлен для VZP {vzp_id}")
    except Exception as e:
        print(f"❌ Ошибка автопинга: {e}")

@bot.tree.command(name="start_vzp", description="Запустить VZP (создать категорию и каналы)")
@app_commands.describe(vzp_id="ID VZP")
async def start_vzp(interaction: discord.Interaction, vzp_id: str):
    if not await is_allowed_channel(interaction):
        await interaction.response.send_message(
            f"❌ Эту команду можно использовать только в канале <#{ALLOWED_CHANNEL}>!",
            ephemeral=True
        )
        return
    
    if not await has_high_role(interaction):
        await interaction.response.send_message(
            "❌ У вас нет прав для запуска VZP!",
            ephemeral=True
        )
        return
    
    if vzp_id not in active_vzp:
        await interaction.response.send_message(
            f"❌ VZP с ID `{vzp_id}` не найдена!",
            ephemeral=True
        )
        return
    
    # Отвечаем сразу, чтобы Discord знал, что бот обрабатывает команду
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    vzp_data = active_vzp[vzp_id]
    vzp_data.status = 'VZP IN PROCESS'
    
    await update_vzp_message(vzp_id)
    
    guild = interaction.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True)
    }
    
    members_to_move = []
    for user_id in vzp_data.plus_users:
        member = guild.get_member(user_id)
        if member:
            overwrites[member] = discord.PermissionOverwrite(view_channel=True)
            members_to_move.append(member)
    
    vzp_swaps = swap_history.get(vzp_id, {})
    for new_user_id in vzp_swaps.values():
        member = guild.get_member(new_user_id)
        if member:
            overwrites[member] = discord.PermissionOverwrite(view_channel=True)
            members_to_move.append(member)
    
    category = await guild.create_category_channel(
        name=f"VZP ID - {vzp_id}",
        overwrites=overwrites
    )
    
    vzp_data.category_id = category.id
    voice_channel = await category.create_voice_channel(name="vzp voice")
    await category.create_text_channel(name="vzp flood")
    await category.create_text_channel(name="vzp call")
    
    moved_count = 0
    for member in members_to_move:
        if member.voice and member.voice.channel:
            try:
                await member.move_to(voice_channel)
                moved_count += 1
            except:
                pass
        await asyncio.sleep(0.1)
    
    notified = await notify_users_ls(
        vzp_id,
        "🎮 VZP НАЧАЛАСЬ!",
        f"VZP началась! Присоединяйтесь к голосовому каналу:\n{voice_channel.mention}",
        guild
    )
    
    save_data()
    
    # Отправляем финальный ответ
    await interaction.followup.send(
        f"VZP `{vzp_id}` запущена! Создана категория с каналами.\n"
        f"Перемещено в голосовой: {moved_count}/{len(members_to_move)} игроков\n"
        f"Отправлено уведомлений: {notified}",
        ephemeral=True
    )

@bot.tree.command(name="stop_reactions", description="Остановить приём заявок на VZP")
@app_commands.describe(vzp_id="ID VZP")
async def stop_reactions(interaction: discord.Interaction, vzp_id: str):
    if not await is_allowed_channel(interaction):
        await interaction.response.send_message(
            f"❌ Эту команду можно использовать только в канале <#{ALLOWED_CHANNEL}>!",
            ephemeral=True
        )
        return
    
    if not await has_high_role(interaction):
        await interaction.response.send_message(
            "❌ У вас нет прав для этой команды!",
            ephemeral=True
        )
        return
    
    if vzp_id not in active_vzp:
        await interaction.response.send_message(
            f"❌ VZP с ID `{vzp_id}` не найдена!",
            ephemeral=True
        )
        return
    
    vzp_data = active_vzp[vzp_id]
    
    if vzp_data.status != 'OPEN':
        await interaction.response.send_message(
            f"❌ VZP уже не в статусе OPEN! Текущий статус: {vzp_data.status}",
            ephemeral=True
        )
        return
    
    vzp_data.status = 'LIST IN PROCESS'
    await update_vzp_message(vzp_id)
    save_data()

@bot.tree.command(name="return_reactions", description="Возобновить приём заявок на VZP")
@app_commands.describe(vzp_id="ID VZP")
async def return_reactions(interaction: discord.Interaction, vzp_id: str):
    if not await is_allowed_channel(interaction):
        await interaction.response.send_message(
            f"❌ Эту команду можно использовать только в канале <#{ALLOWED_CHANNEL}>!",
            ephemeral=True
        )
        return
    
    if not await has_high_role(interaction):
        await interaction.response.send_message(
            "❌ У вас нет прав для этой команды!",
            ephemeral=True
        )
        return
    
    if vzp_id not in active_vzp:
        await interaction.response.send_message(
            f"❌ VZP с ID `{vzp_id}` не найдена!",
            ephemeral=True
        )
        return
    
    vzp_data = active_vzp[vzp_id]
    
    if vzp_data.status not in ['LIST IN PROCESS', 'VZP IN PROCESS']:
        await interaction.response.send_message(
            f"❌ VZP не в статусе LIST IN PROCESS! Текущий статус: {vzp_data.status}",
            ephemeral=True
        )
        return
    
    if vzp_data.status == 'VZP IN PROCESS':
        await interaction.response.send_message(
            f"❌ Невозможно возобновить набор, VZP уже запущена!",
            ephemeral=True
        )
        return
    
    vzp_data.status = 'OPEN'
    await update_vzp_message(vzp_id)
    save_data()

@bot.tree.command(name="swap_player", description="Заменить игрока в VZP")
@app_commands.describe(
    vzp_id="ID VZP",
    old_player="Игрок, которого нужно заменить",
    new_player="Игрок, который заменит"
)
async def swap_player(interaction: discord.Interaction, vzp_id: str, old_player: discord.Member, new_player: discord.Member):
    if not await has_high_role(interaction):
        await interaction.response.send_message(
            "❌ У вас нет прав для этой команды!",
            ephemeral=True
        )
        return
    
    if vzp_id not in active_vzp:
        await interaction.response.send_message(
            f"❌ VZП с ID `{vzp_id}` не найдена!",
            ephemeral=True
        )
        return
    
    # Отвечаем сразу
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    vzp_data = active_vzp[vzp_id]
    
    if old_player.id not in vzp_data.plus_users:
        await interaction.followup.send(
            f"❌ Игрок {old_player.mention} не найден в списке VZП `{vzp_id}`!",
            ephemeral=True
        )
        return
    
    if new_player.id in vzp_data.plus_users:
        await interaction.followup.send(
            f"❌ Игрок {new_player.mention} уже в основном списке VZП!",
            ephemeral=True
        )
        return
    
    new_player_tier = await get_user_tier(new_player)
    if not new_player_tier:
        await interaction.followup.send(
            f"❌ У игрока {new_player.mention} нет необходимой роли для участия в VZП!",
            ephemeral=True
        )
        return
    
    del vzp_data.plus_users[old_player.id]
    
    if vzp_id not in swap_history:
        swap_history[vzp_id] = {}
    swap_history[vzp_id][old_player.id] = new_player.id
    
    if vzp_data.category_id and vzp_data.status == 'VZP IN PROCESS':
        category = interaction.guild.get_channel(vzp_data.category_id)
        if category:
            try:
                await category.set_permissions(old_player, overwrite=None)
                await category.set_permissions(
                    new_player,
                    view_channel=True,
                    connect=True,
                    speak=True
                )
                
                voice_channels = [ch for ch in category.voice_channels if isinstance(ch, discord.VoiceChannel)]
                for voice_channel in voice_channels:
                    if old_player in voice_channel.members:
                        try:
                            await old_player.move_to(None)
                        except:
                            pass
            except Exception as e:
                print(f"⚠️ Ошибка обновления прав: {e}")
    
    await update_vzp_message(vzp_id)
    
    success_embed = discord.Embed(
        title="ЗАМЕНА ИГРОКА ВЫПОЛНЕНА",
        color=0x00FF00,
        timestamp=datetime.now()
    )
    
    success_embed.add_field(
        name="ИГРОКИ",
        value=f"**Удален:** {old_player.mention}\n"
              f"**Добавлен:** {new_player.mention}",
        inline=False
    )
    
    success_embed.set_footer(text=f"Выполнено: {interaction.user.display_name} | {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    
    await interaction.followup.send(embed=success_embed, ephemeral=True)
    
    try:
        old_embed = discord.Embed(
            title="ВЫ ЗАМЕНЕНЫ В VZП",
            color=0xFFA500,
            timestamp=datetime.now()
        )
        old_embed.add_field(name="ID VZП", value=vzp_id, inline=False)
        old_embed.add_field(name="Время", value=vzp_data.time, inline=True)
        old_embed.add_field(name="Ваша замена", value=new_player.display_name, inline=False)
        old_embed.add_field(name="Статус", value="Заменили", inline=True)
        old_embed.set_footer(text=f"VZП Manager | {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        await old_player.send(embed=old_embed)
    except:
        pass
    
    try:
        new_embed = discord.Embed(
            title="ВЫ ЗАМЕНИЛИ ИГРОКА В VZП",
            color=0x00FF00,
            timestamp=datetime.now()
        )
        new_embed.add_field(name="ID VZП", value=vzp_id, inline=False)
        new_embed.add_field(name="Время", value=vzp_data.time, inline=True)
        new_embed.add_field(name="Вы заменили", value=old_player.display_name, inline=False)
        new_embed.add_field(name="Статус", value="Вы в списке", inline=True)
        new_embed.set_footer(text=f"VZП Manager | {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        await new_player.send(embed=new_embed)
    except:
        pass
    
    save_data()

@bot.tree.command(name="close_vzp", description="Закрыть VZP (удалить категорию, уведомить и записать результат)")
@app_commands.describe(
    vzp_id="ID VZP",
    enemy="Имя противника",
    result="Результат VZП",
    amount="Количество точек"
)
@app_commands.choices(
    result=[
        app_commands.Choice(name="WIN", value="win"),
        app_commands.Choice(name="LOSE", value="lose"),
    ]
)
async def close_vzp(interaction: discord.Interaction, vzp_id: str, enemy: str, result: app_commands.Choice[str], amount: int):
    if not await is_allowed_channel(interaction):
        await interaction.response.send_message(
            f"❌ Эту команду можно использовать только в канале <#{ALLOWED_CHANNEL}>!",
            ephemeral=True
        )
        return
    
    if not await has_high_role(interaction):
        await interaction.response.send_message(
            "❌ У вас нет прав для закрытия VZP!",
            ephemeral=True
        )
        return
    
    if vzp_id not in active_vzp:
        await interaction.response.send_message(
            f"❌ VZP с ID `{vzp_id}` не найдена!",
            ephemeral=True
        )
        return
    
    # Отвечаем сразу, чтобы Discord знал, что бот обрабатывает команду
    await interaction.response.defer(thinking=True, ephemeral=True)
    
    vzp_data = active_vzp[vzp_id]
    
    vzp_data.enemy = enemy
    vzp_data.status = 'CLOSED'
    vzp_data.result = result.value
    vzp_data.amount = amount
    
    await update_vzp_message(vzp_id)
    
    guild = interaction.guild
    deleted_count = 0
    
    if vzp_data.category_id:
        try:
            category = guild.get_channel(vzp_data.category_id)
            if category:
                for channel in category.channels:
                    try:
                        await channel.delete()
                        deleted_count += 1
                        await asyncio.sleep(0.1)
                    except:
                        pass
                
                try:
                    await category.delete()
                    deleted_count += 1
                except:
                    pass
        except:
            pass
    
    participants_count = await post_vzp_result(vzp_id, result.value, amount, guild)
    
    closed_vzp[vzp_id] = {
        'time': vzp_data.time,
        'enemy': vzp_data.enemy,
        'members': vzp_data.members,
        'result': result.value,
        'amount': amount,
        'participants': len(vzp_data.plus_users),
        'all_participants': participants_count,
        'closed_at': datetime.now().isoformat()
    }
    
    del active_vzp[vzp_id]
    
    if vzp_id in swap_history:
        del swap_history[vzp_id]
    
    if vzp_id in position_assignments:
        del position_assignments[vzp_id]
    
    if vzp_id in position_messages:
        del position_messages[vzp_id]
    
    save_data()
    
    # Отправляем финальный ответ
    await interaction.followup.send(
        f"VZP `{vzp_id}` успешно закрыта!\n"
        f"Результат: **{result.name}**\n"
        f"Противник: **{enemy}**\n"
        f"Точки: **{amount}**\n"
        ephemeral=True
    )

@bot.tree.command(name="del_list", description="Удалить пользователя(ей) из списка VZP")
@app_commands.describe(
    members="Пользователи (можно выбрать нескольких)",
    vzp_id="ID VZP"
)
async def del_list(interaction: discord.Interaction, members: str, vzp_id: str):
    if not await is_allowed_channel(interaction):
        await interaction.response.send_message(
            f"❌ Эту команду можно использовать только в канале <#{ALLOWED_CHANNEL}>!",
            ephemeral=True
        )
        return
    
    if not await has_high_role(interaction):
        await interaction.response.send_message(
            "❌ У вас нет прав для этой команды!",
            ephemeral=True
        )
        return
    
    if vzp_id not in active_vzp:
        await interaction.response.send_message(
            f"❌ VZP с ID `{vzp_id}` не найдена!",
            ephemeral=True
        )
        return
    
    vzp_data = active_vzp[vzp_id]
    
    member_ids = []
    for part in members.split():
        if part.startswith('<@') and part.endswith('>'):
            try:
                member_id = int(part.strip('<@!>'))
                member_ids.append(member_id)
            except:
                pass
    
    if not member_ids:
        await interaction.response.send_message(
            "❌ Не удалось найти упоминания пользователей!",
            ephemeral=True
        )
        return
    
    deleted_members = []
    
    for member_id in member_ids:
        if member_id not in vzp_data.plus_users:
            continue
        
        del vzp_data.plus_users[member_id]
        
        if vzp_id in swap_history:
            if member_id in swap_history[vzp_id].values():
                key_to_remove = None
                for k, v in swap_history[vzp_id].items():
                    if v == member_id:
                        key_to_remove = k
                        break
                if key_to_remove:
                    del swap_history[vzp_id][key_to_remove]
            
            if member_id in swap_history[vzp_id]:
                del swap_history[vzp_id][member_id]
        
        deleted_members.append(member_id)
        
        try:
            member = interaction.guild.get_member(member_id)
            if member:
                notify_embed = discord.Embed(
                    title="❌ ВАС УДАЛИЛИ ИЗ СПИСКА VZP",
                    color=discord.Color.red()
                )
                notify_embed.add_field(name="ID VZP", value=vzp_id, inline=False)
                notify_embed.add_field(name="Причина", value="Удалён администратором", inline=False)
                await member.send(embed=notify_embed)
        except:
            pass
    
    if not deleted_members:
        await interaction.response.send_message(
            "❌ Указанные пользователи не найдены в списке VZP!",
            ephemeral=True
        )
        return
    
    await update_vzp_message(vzp_id)
    save_data()
    
    members_text = ", ".join([f"<@{id}>" for id in deleted_members])
    await interaction.response.send_message(
        f"✅ Удалены из VZP `{vzp_id}`: {members_text}",
        ephemeral=True
    )

@bot.tree.command(name="add_vzp", description="Добавить пользователя в VZP")
@app_commands.describe(
    vzp_id="ID VZP",
    member="Пользователь"
)
async def add_vzp(interaction: discord.Interaction, vzp_id: str, member: discord.Member):
    if not await is_allowed_channel(interaction):
        await interaction.response.send_message(
            f"❌ Эту команду можно использовать только в канале <#{ALLOWED_CHANNEL}>!",
            ephemeral=True
        )
        return
    
    if not await has_high_role(interaction):
        await interaction.response.send_message(
            "❌ У вас нет прав для этой команды!",
            ephemeral=True
        )
        return
    
    if vzp_id not in active_vzp:
        await interaction.response.send_message(
            f"❌ VZP с ID `{vzp_id}` не найдена!",
            ephemeral=True
        )
        return
    
    vzp_data = active_vzp[vzp_id]
    
    if vzp_data.status == 'CLOSED':
        await interaction.response.send_message(
            f"❌ VZP уже закрыта! Нельзя добавить игрока.",
            ephemeral=True
        )
        return
    
    if member.id in vzp_data.plus_users:
        await interaction.response.send_message(
            f"❌ Игрок {member.mention} уже в списке этой VZP!",
            ephemeral=True
        )
        return
    
    tier = await get_user_tier(member)
    if not tier:
        await interaction.response.send_message(
            f"❌ У игрока {member.mention} нет необходимой роли для участия в VZP!",
            ephemeral=True
        )
        return
    
    vzp_data.plus_users[member.id] = tier
    
    # Выдача прав категории, если VZP запущена
    if vzp_data.category_id and vzp_data.status == 'VZP IN PROCESS':
        category = interaction.guild.get_channel(vzp_data.category_id)
        if category:
            try:
                await category.set_permissions(
                    member,
                    view_channel=True,
                    connect=True,
                    speak=True
                )
            except Exception as e:
                print(f"⚠️ Ошибка выдачи прав категории: {e}")
    
    await update_vzp_message(vzp_id)
    save_data()
    
    try:
        notify_embed = discord.Embed(
            title="✅ ВАС ДОБАВИЛИ В VZP",
            color=discord.Color.green()
        )
        notify_embed.add_field(name="ID VZP", value=vzp_id, inline=False)
        notify_embed.add_field(name="Время", value=vzp_data.time, inline=False)
        notify_embed.add_field(name="Добавил", value=interaction.user.display_name, inline=False)
        notify_embed.add_field(name="Статус", value=vzp_data.status, inline=False)
        await member.send(embed=notify_embed)
    except:
        pass
    
    await interaction.response.send_message(
        f"✅ {member.mention} добавлен в VZP `{vzp_id}`!",
        ephemeral=True
    )

@bot.tree.command(name="call_vzp", description="Создать распределение позиций")
@app_commands.describe(
    positions="Количество позиций (от 1 до 100)",
    vzp_id="ID VZP (не обязательно)"
)
async def call_vzp(interaction: discord.Interaction, positions: int, vzp_id: str = None):
    if not await has_high_role(interaction):
        await interaction.response.send_message(
            "❌ У вас нет прав для этой команды!",
            ephemeral=True
        )
        return
    
    if positions < 1 or positions > 100:
        await interaction.response.send_message(
            "❌ Количество позиций должно быть от 1 до 100!",
            ephemeral=True
        )
        return
    
    if vzp_id and vzp_id not in active_vzp:
        await interaction.response.send_message(
            f"❌ VZP с ID `{vzp_id}` не найдена!",
            ephemeral=True
        )
        return
    
    pos_id = f"POS_{str(uuid.uuid4())[:8]}"
    
    position_assignments[pos_id] = {i: None for i in range(1, positions + 1)}
    
    active_position_calls[interaction.channel_id] = {
        "pos_id": pos_id,
        "vzp_id": vzp_id,
        "created_by": interaction.user.id,
        "created_at": datetime.now().isoformat()
    }
    
    position_messages[pos_id] = {
        "message_id": 0,
        "channel_id": interaction.channel_id
    }
    
    lines = []
    for i in range(1, positions + 1):
        lines.append(f"{i} - ...")
    
    embed = discord.Embed(
        title="🎯 РАСПРЕДЕЛЕНИЕ ПОЗИЦИЙ",
        description="\n".join(lines),
        color=discord.Color.blue()
    )
    
    if vzp_id:
        embed.title = f"🎯 РАСПРЕДЕЛЕНИЕ ПОЗИЦИЙ VZP {vzp_id}"
        vzp_data = active_vzp[vzp_id]
        embed.add_field(
            name="📅 ИНФОРМАЦИЯ О VZP",
            value=f"**Время:** {vzp_data.time}\n"
                  f"**Статус:** {vzp_data.status}\n"
                  f"**Участников:** {len(vzp_data.plus_users)}/{vzp_data.members}",
            inline=False
        )
    
    embed.add_field(
        name="📝 КАК ЗАПИСАТЬСЯ",
        value="**Отправьте в этот канал номер позиции, которую хотите занять (например: `5`)**\n"
              "**Чтобы освободить позицию, отправьте `отмена` или `cancel`**",
        inline=False
    )
    
    embed.set_footer(text=f"Создано: {interaction.user.display_name} | Всего позиций: {positions}")
    
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()
    
    position_messages[pos_id]["message_id"] = message.id
    
    save_data()

@bot.tree.command(name="clear_positions", description="Очистить все позиции в текущем канале")
async def clear_positions(interaction: discord.Interaction):
    if not await has_high_role(interaction):
        await interaction.response.send_message(
            "❌ У вас нет прав для этой команды!",
            ephemeral=True
        )
        return
    
    if interaction.channel_id not in active_position_calls:
        await interaction.response.send_message(
            "❌ В этом канале нет активного распределения позиций!",
            ephemeral=True
        )
        return
    
    pos_info = active_position_calls[interaction.channel_id]
    pos_id = pos_info["pos_id"]
    
    for pos in position_assignments.get(pos_id, {}):
        position_assignments[pos_id][pos] = None
    
    await update_position_message(pos_id)
    await interaction.response.send_message("✅ Все позиции очищены!", ephemeral=True)

@bot.tree.command(name="close_positions", description="Завершить набор позиций в текущем канале")
async def close_positions(interaction: discord.Interaction):
    if not await has_high_role(interaction):
        await interaction.response.send_message(
            "❌ У вас нет прав для этой команды!",
            ephemeral=True
        )
        return
    
    if interaction.channel_id not in active_position_calls:
        await interaction.response.send_message(
            "❌ В этом канале нет активного распределения позиций!",
            ephemeral=True
        )
        return
    
    pos_info = active_position_calls[interaction.channel_id]
    pos_id = pos_info["pos_id"]
    
    del active_position_calls[interaction.channel_id]
    
    positions = position_assignments.get(pos_id, {})
    occupied = [pos for pos, member in positions.items() if member]
    
    embed = discord.Embed(
        title="✅ НАБОР ПОЗИЦИЙ ЗАВЕРШЕН",
        color=discord.Color.green()
    )
    
    if pos_info["vzp_id"]:
        embed.add_field(
            name="VZP",
            value=f"ID: `{pos_info['vzp_id']}`",
            inline=False
        )
    
    embed.add_field(
        name="📊 СТАТИСТИКА",
        value=f"**Всего позиций:** {len(positions)}\n"
              f"**Занято:** {len(occupied)}\n"
              f"**Свободно:** {len(positions) - len(occupied)}",
        inline=False
    )
    
    occupied_list = []
    for pos in sorted(positions.keys()):
        member = positions[pos]
        if member:
            occupied_list.append(f"{pos} - {member.mention}")
    
    if occupied_list:
        embed.add_field(
            name="🎮 ЗАНЯТЫЕ ПОЗИЦИИ",
            value="\n".join(occupied_list),
            inline=False
        )
    
    embed.set_footer(text=f"Завершил: {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="list_vzp", description="Показать активные VZP")
async def list_vzp(interaction: discord.Interaction):
    if not active_vzp:
        await interaction.response.send_message("📭 Нет активных VZP", ephemeral=True)
        return
    
    embed = discord.Embed(title="📋 АКТИВНЫЕ VZP", color=discord.Color.blue())
    
    for vzp_id, vzp_data in active_vzp.items():
        status = vzp_data.status
        status_emoji = {
            'OPEN': '🟢',
            'LIST IN PROCESS': '🟡',
            'VZP IN PROCESS': '🔵',
            'CLOSED': '🔴'
        }.get(status, '⚪')
        
        created_date = datetime.fromisoformat(vzp_data.created_at).strftime("%d.%m %H:%M")
        
        embed.add_field(
            name=f"**{vzp_id}** {status_emoji}",
            value=f"**Время:** {vzp_data.time}\n"
            f"**Создана:** {created_date}\n"
            f"**Тип:** {vzp_data.attack_def_name.split(' ')[1]}\n"
            f"**Условия:** {', '.join(vzp_data.conditions_display)}\n"
            f"**Калибры:** {' + '.join(vzp_data.caliber_names)}\n"
            f"**Участники:** {len(vzp_data.plus_users)}/{vzp_data.members}\n"
            f"**Статус:** {status}\n"
            f"**--------------------------------------**",
        inline=False
    )
    
    embed.set_footer(text=f"Всего активных VZP: {len(active_vzp)}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="ping", description="Пингануть всех участников")
async def ping(interaction: discord.Interaction):
    if not await has_high_role(interaction):
        await interaction.response.send_message(
            "❌ У вас нет прав для этой команды!",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        for i in range(5):
            await interaction.channel.send("@everyone")
            await asyncio.sleep(0.2)
    except Exception as e:
        await interaction.followup.send(
            f"❌ Ошибка отправки: {e}",
            ephemeral=True
        )
        return
    
    await interaction.followup.send("✅ Пинги отправлены!", ephemeral=True)

@bot.tree.command(name="voice_status", description="Показать статус игроков в голосовом канале VZP")
async def voice_status(interaction: discord.Interaction):
    channel = interaction.channel
    
    if not hasattr(channel, 'category') or channel.category is None:
        await interaction.response.send_message(
            "❌ Эта команда работает только в каналах внутри категории VZP!",
            ephemeral=True
        )
        return
    
    category = channel.category
    
    if "VZP ID - " not in category.name:
        await interaction.response.send_message(
            "❌ Эта команда работает только в каналах внутри категории VZP! Текущая категория не является VZP категорией.",
            ephemeral=True
        )
        return
    
    try:
        vzp_id = category.name.split("VZP ID - ")[1].strip()
    except:
        await interaction.response.send_message(
            "❌ Не удалось определить VZP ID из названия категории!",
            ephemeral=True
        )
        return
    
    if vzp_id not in active_vzp:
        await interaction.response.send_message(
            f"❌ VZP с ID `{vzp_id}` не найдена в активных VZP!",
            ephemeral=True
        )
        return
    
    vzp_data = active_vzp[vzp_id]
    
    if vzp_data.status != 'VZP IN PROCESS':
        await interaction.response.send_message(
            f"❌ Эта VZP еще не запущена! Текущий статус: {vzp_data.status}",
            ephemeral=True
        )
        return
    
    if vzp_data.category_id != category.id:
        await interaction.response.send_message(
            "❌ ID категории не совпадает с сохраненной категорией VZP!",
            ephemeral=True
        )
        return
    
    all_players = set(vzp_data.plus_users.keys())
    
    vzp_swaps = swap_history.get(vzp_id, {})
    for new_user_id in vzp_swaps.values():
        all_players.add(new_user_id)
    
    players_in_voice = set()
    
    voice_channels = [ch for ch in category.channels if isinstance(ch, discord.VoiceChannel)]
    for voice_channel in voice_channels:
        for member in voice_channel.members:
            players_in_voice.add(member.id)
    
    embed = discord.Embed(
        title=f"ГОЛОСОВАЯ АКТИВНОСТЬ VZP {vzp_id}",
        color=discord.Color.purple(),
        timestamp=datetime.now()
    )
    
    attack_def_display = vzp_data.attack_def_name.split(' ')[1] if ' ' in vzp_data.attack_def_name else vzp_data.attack_def_name
    
    embed.add_field(
        name="ИНФОРМАЦИЯ",
        value=f"**Участников:** {len(all_players)}\n"
              f"**В голосовом:** {len(players_in_voice)}/{len(all_players)}",
        inline=False
    )
    
    players_list = []
    sorted_players = sorted(all_players)
    
    for i, user_id in enumerate(sorted_players, 1):
        member = interaction.guild.get_member(user_id)
        if member:
            status_circle = "🟢" if user_id in players_in_voice else "🔴"
            players_list.append(f"{i} - {member.mention} {status_circle}")
        else:
            players_list.append(f"{i} - <@{user_id}> 🔴")
    
    if players_list:
        players_text = "\n".join(players_list)
        
        if len(players_text) > 1024:
            chunk_size = 20
            chunks = [players_list[i:i + chunk_size] for i in range(0, len(players_list), chunk_size)]
            
            for i, chunk in enumerate(chunks, 1):
                chunk_text = "\n".join(chunk)
                embed.add_field(
                    name=f"👥 УЧАСТНИКИ (часть {i})" if len(chunks) > 1 else "👥 УЧАСТНИКИ",
                    value=chunk_text,
                    inline=False
                )
        else:
            embed.add_field(
                name="👥 УЧАСТНИКИ",
                value=players_text,
                inline=False
            )
    
    vzp_swaps = swap_history.get(vzp_id, {})
    if vzp_swaps:
        swap_list = []  # Переименовано с swap_info на swap_list для согласованности
        for old_user_id, new_user_id in vzp_swaps.items():
            old_member = interaction.guild.get_member(old_user_id)
            new_member = interaction.guild.get_member(new_user_id)
            
            old_name = old_member.mention if old_member else f"<@{old_user_id}>"
            new_name = new_member.mention if new_member else f"<@{new_user_id}>"
            
            status_circle = "🟢" if new_user_id in players_in_voice else "🔴"
            swap_list.append(f"• {new_name} {status_circle} → {old_name}")
        
        if swap_list:  # Исправлено с swap_info на swap_list
            embed.add_field(
                name="**🔄 ЗАМЕНЫ**",
                value="\n".join(swap_list),
                inline=False
            )
    
    embed.description = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
    
    embed.set_footer(text=f"Категория: {category.name} | Обновлено: {datetime.now().strftime('%H:%M:%S')}")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="help_vzp", description="Помощь по командам VZP бота")
async def help_vzp(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 ПОМОЩЬ ПО КОМАНДАМ VZP БОТА",
        color=discord.Color.purple()
    )
    
    commands_list = [
        ("`/vzp_start`", "Создать новую VZP с условиями забива", f"Только в <#{ALLOWED_CHANNEL}>"),
        ("`/start_vzp`", "Запустить VZP (создать категорию)", f"Только в <#{ALLOWED_CHANNEL}>"),
        ("`/close_vzp`", "Закрыть VZP (удалить категорию и записать результат)", f"Только в <#{ALLOWED_CHANNEL}>"),
        ("`/stop_reactions`", "Остановить приём заявок", f"Только в <#{ALLOWED_CHANNEL}>"),
        ("`/return_reactions`", "Возобновить приём заявок", f"Только в <#{ALLOWED_CHANNEL}>"),
        ("`/swap_player`", "Заменить игрока в VZP", f"Только в <#{ALLOWED_CHANNEL}>"),
        ("`/del_list`", "Удалить пользователя(ей) из списка", f"Только в <#{ALLOWED_CHANNEL}>"),
        ("`/add_vzp`", "Добавить пользователя в VZP (работает даже во время VZP)", f"Только в <#{ALLOWED_CHANNEL}>"),
        ("`/call_vzp`", "Создать распределение позиций", "✅ РАБОТАЕТ ВЕЗДЕ"),
        ("`/clear_positions`", "Очистить все позиции в канале", "✅ РАБОТАЕТ ВЕЗДЕ"),
        ("`/close_positions`", "Завершить набор позиций", "✅ РАБОТАЕТ ВЕЗДЕ"),
        ("`/ping`", "Пингануть всех участников VZP", "✅ РАБОТАЕТ ВЕЗДЕ (отправляет 5 раз @everyone)"),
        ("`/list_vzp`", "Показать активные VZP", "✅ РАБОТАЕТ ВЕЗДЕ"),
        ("`/voice_status`", "Показать статус игроков в голосовом канале VZP", "✅ Определяет VZP ID автоматически по категории канала"),
        ("`/help_vzp`", "Эта справка", "✅ РАБОТАЕТ ВЕЗДЕ")
    ]
    
    for cmd, desc, example in commands_list:
        embed.add_field(name=f"{cmd}", value=f"**Описание:** {desc}\n**Использование:** {example}", inline=False)
    
    embed.add_field(
        name="📊 СТАТУСЫ VZP",
        value="```\n🟢 OPEN - набор открыт\n🟡 LIST IN PROCESS - список формируется\n🔵 VZP IN PROCESS - VZP идёт\n🔴 CLOSED - VZP завершена\n```",
        inline=False
    )
    
    embed.add_field(
        name="🎯 СТАТУС ГОЛОСОВОЙ АКТИВНОСТИ",
        value="🟢 - Игрок в голосовом канале\n🔴 - Игрок не в голосовом канале",
        inline=False
    )
    
    embed.add_field(
        name="📝 РАСПРЕДЕЛЕНИЕ ПОЗИЦИЙ",
        value="• `/call_vzp positions:10` - создать распределение на 10 позиций\n"
              "• `/call_vzp positions:10 vzp_id:abc123` - создать распределение для VZP\n"
              "• **Отправьте цифру в канал**, чтобы занять позицию\n"
              "• **Отправьте `отмена`**, чтобы освободить позицию",
        inline=False
    )
    
    embed.set_footer(text="Бот автоматически сохраняет все данные")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ===================== ЗАПУСК =====================
@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен!')
    print(f'👑 ID бота: {bot.user.id}')
    print(f'📊 Серверов: {len(bot.guilds)}')
    print(f'📁 Активных VZP: {len(active_vzp)}')
    print(f'🎯 Активных распределений: {len(active_position_calls)}')
    print('=' * 50)
    print('Доступные команды:')
    print('   /vzp_start - создать VZP (только в разрешенном канале)')
    print('   /start_vzp - запустить VZP (только в разрешенном канале)')
    print('   /close_vzp - закрыть VZP с результатом и точками (только в разрешенном канале)')
    print('   /stop_reactions - остановить заявки (только в разрешенном канале)')
    print('   /return_reactions - возобновить заявки (только в разрешенном канале)')
    print('   /swap_player - заменить игрока (только в разрешенном канале)')
    print('   /del_list - удалить из списка (можно нескольких, только в разрешенном канале)')
    print('   /add_vzp - добавить игрока в VZP (работает даже во время VZP, только в разрешенном канале)')
    print('   /call_vzp - создать распределение позиций (работает везде, до 100 позиций)')
    print('   /clear_positions - очистить все позиции в канале (работает везде)')
    print('   /close_positions - завершить набор позиций (работает везде)')
    print('   /ping - пингануть всех (работает везде, отправляет 5 раз @everyone)')
    print('   /list_vzp - список VZP (работает везде)')
    print('   /voice_status - статус голосовой активности (работает везде)')
    print('   /help_vzp - помощь (работает везде)')
    print('=' * 50)
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(active_vzp)} активных VZP"
        )
    )

if __name__ == "__main__":
    print("🚀 Запуск бота VZP Manager...")
    print("📂 Загрузка сохраненных данных...")
    
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
        save_data()
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        save_data()