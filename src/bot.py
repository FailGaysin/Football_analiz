import asyncio
import re
import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# ============ НАСТРОЙКИ ============
BOT_TOKEN = os.environ['8567561708:AAGAKZX-tYwQgAhRqsbfg9aKet3141ECUvQ']
CHANNEL_ID = os.environ['@FotballabtoF']
BASE_PATH = "/tmp"
# ===================================

TEAM_NAME_FIXES = {
    "Borussia Mönchengladbach": "Borussia M.Gladbach",
    "FC Köln": "FC Cologne",
    "Athletic Club": "Athletic Bilbao",
    "Paris Saint-Germain": "Paris Saint Germain",
    "Parma": "Parma Calcio 1913",
    "Rennes": "Stade Rennais",
    "Le Havre": "Le Havre AC",
    "Atletico Madrid": "Atlético Madrid",
    "Alaves": "Deportivo Alavés",
    "Verona": "Hellas Verona",
    "Lecce": "US Lecce",
    "Athletic Club": "Athletic Bilbao",
    "Koln": "FC Cologne",
    "PSG": "Paris Saint Germain",
    "Borussia M.Gladbach": "Borussia M.Gladbach",
    "Manchester United": "Manchester United",
    "Real Madrid": "Real Madrid",
    "Barcelona": "Barcelona",
    "Bayern Munich": "Bayern Munich",
    "Inter": "Inter",
    "AC Milan": "AC Milan",
    "AS Roma": "AS Roma",
    "Atalanta": "Atalanta",
    "Lazio": "Lazio",
    "Fiorentina": "Fiorentina",
    "Napoli": "Napoli",
    "Juventus": "Juventus",
    "Torino": "Torino",
    "Bologna": "Bologna",
    "Monza": "Monza",
    "Verona": "Verona",
    "Lecce": "Lecce",
    "Cagliari": "Cagliari",
    "Empoli": "Empoli",
    "Udinese": "Udinese",
    "Frosinone": "Frosinone",
    "Sassuolo": "Sassuolo",
    "Salernitana": "Salernitana",
    "Wolverhampton Wanderers": "Wolves",
    "Newcastle United": "Newcastle",
    "Stade Brestois 29": "Brest",
    "Hellas Verona": "Verona",
}

LEAGUE_STATS = {}
SCORERS_DATA = {}

def download_understat_data():
    """Скачивает актуальные CSV-файлы с understat"""
    print("🔄 Загружаем данные с understat...")
    
    leagues = {
        "EPL": ("АПЛ", "premier_league_stats.csv"),
        "La_liga": ("Ла Лига", "la_liga_stats.csv"),
        "Bundesliga": ("Бундеслига", "bundesliga_stats.csv"),
        "Serie_A": ("Серия А", "serie_a_stats.csv"),
        "Ligue_1": ("Лига 1", "ligue_1_stats.csv")
    }
    
    for understat_key, (name, filename) in leagues.items():
        try:
            url = f"https://understat.com/league/{understat_key}/2025"
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            
            # Извлекаем teamsData
            match = re.search(r"var teamsData\s*=\s*(\{.*?\});", res.text, re.DOTALL)
            if not match:
                continue
                
            data_str = match.group(1)
            data = eval(data_str)  # understat использует Python-совместимый формат
            
            filepath = os.path.join(BASE_PATH, filename)
            with open(filepath, 'w', encoding='utf-8-sig') as f:
                f.write("ID;Team;Matches;Wins;Draws;Loses;Goals;GA;Points;xG;xGA;xPTS\n")
                teams_list = []
                for team_id, team in data.items():
                    history = team['history']
                    total = {
                        'games': len(history),
                        'wins': sum(m['wins'] for m in history),
                        'draws': sum(m['draws'] for m in history),
                        'loses': sum(m['loses'] for m in history),
                        'goals': sum(m['scored'] for m in history),
                        'ga': sum(m['missed'] for m in history),
                        'points': sum(m['pts'] for m in history),
                        'xG': sum(m['xG'] for m in history),
                        'xGA': sum(m['xGA'] for m in history),
                        'xPTS': sum(m['xpts'] for m in history)
                    }
                    teams_list.append((team['title'], total))
                
                # Сортируем по очкам
                teams_list.sort(key=lambda x: (x[1]['points'], x[1]['goals']), reverse=True)
                
                for i, (team_name, stats) in enumerate(teams_list, start=1):
                    f.write(
                        f"{i};{team_name};{stats['games']};{stats['wins']};{stats['draws']};"
                        f"{stats['loses']};{stats['goals']};{stats['ga']};{stats['points']};"
                        f"{stats['xG']:.2f};{stats['xGA']:.2f};{stats['xPTS']:.2f}\n"
                    )
            
            # Загружаем в память
            stats_dict = {}
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                next(f)
                for line in f:
                    row = line.strip().split(';')
                    if len(row) >= 12:
                        team_name = row[1].strip()
                        try:
                            stats_dict[team_name] = {
                                'wins': int(row[3]),
                                'draws': int(row[4]),
                                'loses': int(row[5]),
                                'goals': int(row[6]),
                                'ga': int(row[7]),
                                'points': int(row[8]),
                                'xG': float(row[9]),
                                'xGA': float(row[10]),
                                'xPTS': float(row[11])
                            }
                        except:
                            continue
            
            lid_map = {"АПЛ": 39, "Ла Лига": 140, "Бундеслига": 78, "Серия А": 135, "Лига 1": 61}
            LEAGUE_STATS[lid_map[name]] = stats_dict
            print(f"✅ {name}: {len(stats_dict)} команд")
            
        except Exception as e:
            print(f"❌ Ошибка загрузки {name}: {e}")

# === LIVE-прогноз ===
def calculate_live_prediction(home_team, away_team, stats):
    score_diff = 0.0
    minute = stats.get('minute', 45)
    goals_home, goals_away = stats.get('goals', (0, 0))
    shots_on_target_home, shots_on_target_away = stats.get('shots_on_target', (0, 0))
    corners_home, corners_away = stats.get('corners', (0, 0))
    yellow_home, yellow_away = stats.get('yellow_cards', (0, 0))
    red_home, red_away = stats.get('red_cards', (0, 0))
    possession_home, possession_away = stats.get('possession', (50, 50))

    goal_diff = goals_home - goals_away
    if goal_diff > 0:
        if goal_diff >= 2:
            score_diff += 50
        else:
            score_diff += 35
    elif goal_diff < 0:
        if goal_diff <= -2:
            score_diff -= 50
        else:
            score_diff -= 35

    if minute >= 75:
        score_diff *= 1.5
    elif minute <= 15:
        score_diff *= 0.5

    shots_diff = shots_on_target_home - shots_on_target_away
    if shots_diff >= 3:
        score_diff += 15
    elif shots_diff >= 1:
        score_diff += 8
    elif shots_diff <= -3:
        score_diff -= 15
    elif shots_diff <= -1:
        score_diff -= 8

    corner_diff = corners_home - corners_away
    if corner_diff >= 3:
        score_diff += 5
    elif corner_diff <= -3:
        score_diff -= 5

    if red_home > 0:
        score_diff -= 25
    if red_away > 0:
        score_diff += 25

    if yellow_home >= 2:
        score_diff -= 5
    if yellow_away >= 2:
        score_diff += 5

    poss_diff = possession_home - possession_away
    if poss_diff >= 15:
        score_diff += 2
    elif poss_diff <= -15:
        score_diff -= 2

    max_diff = 70
    clamped = max(-max_diff, min(max_diff, score_diff))
    home_prob = 50 + (clamped / max_diff) * 40
    return round(home_prob, 1), round(100 - home_prob, 1)

def parse_live_stats(text):
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if len(lines) < 2:
        return None

    first_line = lines[0]
    teams = None
    if '–' in first_line:
        parts = first_line.split('–')
    elif '-' in first_line:
        parts = first_line.split('-')
    else:
        return None

    if len(parts) >= 2:
        home_team = parts[0].strip()
        away_part = parts[1].strip()
        away_team = away_part.split()[0] if away_part.split() else away_part
        teams = (home_team, away_team)
    else:
        return None

    stats = {'teams': teams}
    idx = 1

    try:
        if idx < len(lines):
            nums = re.findall(r'\d+', lines[idx])
            if len(nums) >= 2:
                stats['goals'] = (int(nums[0]), int(nums[1]))
            idx += 1

        if idx < len(lines):
            nums = re.findall(r'\d+', lines[idx])
            if nums:
                stats['minute'] = int(nums[0])
            idx += 1

        if idx < len(lines):
            nums = re.findall(r'\d+', lines[idx])
            if len(nums) >= 2:
                stats['shots_on_target'] = (int(nums[0]), int(nums[1]))
            idx += 1

        if idx < len(lines):
            nums = re.findall(r'\d+', lines[idx])
            if len(nums) >= 2:
                stats['corners'] = (int(nums[0]), int(nums[1]))
            idx += 1

        if idx < len(lines):
            nums = re.findall(r'\d+', lines[idx])
            if len(nums) >= 2:
                stats['yellow_cards'] = (int(nums[0]), int(nums[1]))
            idx += 1

        if idx < len(lines):
            nums = re.findall(r'\d+', lines[idx])
            if len(nums) >= 2:
                stats['red_cards'] = (int(nums[0]), int(nums[1]))
            idx += 1

        if idx < len(lines):
            nums = re.findall(r'\d+', lines[idx])
            if len(nums) >= 2:
                stats['possession'] = (int(nums[0]), int(nums[1]))

    except Exception:
        pass

    if 'minute' not in stats:
        stats['minute'] = 45
    if 'goals' not in stats:
        stats['goals'] = (0, 0)

    return stats

# === ТОП-МАТЧ ДНЯ ===
def select_super_match(all_matches):
    if not all_matches:
        return None

    best_match = None
    best_prob = 0

    for game_id, match in all_matches.items():
        try:
            home_odds = match['home_odds']
            away_odds = match['away_odds']
            draw_odds = match['draw_odds']

            prob_home = 1 / home_odds
            prob_away = 1 / away_odds
            prob_draw = 1 / draw_odds

            max_prob = max(prob_home, prob_away, prob_draw)

            if max_prob > best_prob:
                best_prob = max_prob
                best_match = {
                    'game_id': game_id,
                    'match': match,
                    'max_prob': round(max_prob * 100, 1)
                }
        except (ZeroDivisionError, TypeError, ValueError):
            continue

    return best_match

def generate_teaser_post(super_match):
    if not super_match:
        return None

    match = super_match['match']
    home = match['home']
    away = match['away']
    league = match['league']
    prob = super_match['max_prob']

    if prob >= 85:
        strength = "🔥 МАКСИМАЛЬНАЯ"
    elif prob >= 75:
        strength = "⚡ Очень высокая"
    elif prob >= 65:
        strength = "📈 Высокая"
    else:
        strength = "📊 Повышенная"

    message = (
        f"🏆 **ТОП-ПРОГНОЗ ДНЯ!**\n\n"
        f"⚔️ **{league}**: {home} – {away}\n\n"
        f"✅ Наш анализ выявил матч с **{strength} проходимостью**!\n"
        f"📊 Вероятность исхода: **{prob}%**\n\n"
        f"🔒 **Какой исход? Кто фаворит?**\n"
        f"👉 Полный разбор с xG, бомбардирами и статистикой —\n"
        f"**только в закрытом канале!**\n\n"
        f"📲 [Подписаться →](https://t.me/ваш_канал)\n\n"
        f"#Прогноз #ТопМатч"
    )
    return message

# === ОСНОВНОЙ ОБРАБОТЧИК ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Анализируем матчи с учётом xG и коэффициентов...")
    
    leagues = {39: "АПЛ", 140: "Ла Лига", 78: "Бундеслига", 135: "Серия А", 61: "Лига 1"}
    all_matches = {}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'X-API-Key': 'm75d5yyd3o97pntw'
    }
    
    for league_id, league_name in leagues.items():
        try:
            url = f"https://api.sstats.net/games/list?LeagueId={league_id}&Upcoming=true&Limit=5"
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                games = resp.json().get('data', [])
                for game in games:
                    game_id = game['id']
                    odds_list = game.get('odds', [])
                    home_odds = away_odds = draw_odds = None
                    for market in odds_list:
                        if market.get('marketId') == 1:
                            for odd in market.get('odds', []):
                                if odd['name'] == 'Home':
                                    home_odds = odd['value']
                                elif odd['name'] == 'Away':
                                    away_odds = odd['value']
                                elif odd['name'] == 'Draw':
                                    draw_odds = odd['value']
                    if home_odds is not None and away_odds is not None and draw_odds is not None:
                        all_matches[game_id] = {
                            'home': game['homeTeam']['name'],
                            'away': game['awayTeam']['name'],
                            'league': league_name,
                            'league_id': league_id,
                            'home_odds': home_odds,
                            'away_odds': away_odds,
                            'draw_odds': draw_odds
                        }
        except Exception as e:
            print(f"⚠️ Ошибка загрузки {league_name}: {e}")
            continue
    
    if not all_matches:
        await update.message.reply_text(
            "❌ Нет матчей с коэффициентами\n"
            "ℹ️ Коэффициенты обычно появляются за 1-3 дня до матча."
        )
        return
    
    context.user_data['matches'] = all_matches
    keyboard = []
    matches_list = list(all_matches.items())[:25]
    for game_id, match_info in matches_list:
        button_text = f"{match_info['league']}: {match_info['home']} – {match_info['away']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"m_{game_id}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👇 Выберите матч:", reply_markup=reply_markup)

# === ОБРАБОТЧИК МАТЧА ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("m_"):
        try:
            game_id = int(query.data.split("_")[1])
            matches = context.user_data.get('matches', {})
            match_info = matches.get(game_id)
            if not match_info:
                await query.edit_message_text("❌ Матч не найден")
                return
            
            home_team = match_info['home']
            away_team = match_info['away']
            league_name = match_info['league']
            home_odds = match_info['home_odds']
            away_odds = match_info['away_odds']
            draw_odds = match_info['draw_odds']
            
            lid_map = {"АПЛ": 39, "Ла Лига": 140, "Бундеслига": 78, "Серия А": 135, "Лига 1": 61}
            understat_id = lid_map.get(league_name)
            
            your_prob_home = your_prob_draw = your_prob_away = None
            home_stat = away_stat = None
            
            if understat_id in LEAGUE_STATS:
                stats = LEAGUE_STATS[understat_id]
                home_fixed = TEAM_NAME_FIXES.get(home_team, home_team)
                away_fixed = TEAM_NAME_FIXES.get(away_team, away_team)
                
                home_stat = stats.get(home_fixed)
                away_stat = stats.get(away_fixed)
                
                if home_stat and away_stat:
                    matches_home = home_stat['wins'] + home_stat['draws'] + home_stat['loses']
                    matches_away = away_stat['wins'] + away_stat['draws'] + away_stat['loses']
                    
                    home_xpts_avg = home_stat['xPTS'] / matches_home if matches_home > 0 else 0
                    away_xpts_avg = away_stat['xPTS'] / matches_away if matches_away > 0 else 0

                    total_xpts = home_xpts_avg + away_xpts_avg
                    if total_xpts > 0:
                        prob_home = home_xpts_avg / total_xpts
                        prob_away = away_xpts_avg / total_xpts
                    else:
                        prob_home = 0.5
                        prob_away = 0.5

                    home_xG_avg = home_stat['xG'] / matches_home if matches_home > 0 else 0
                    away_xG_avg = away_stat['xG'] / matches_away if matches_away > 0 else 0
                    if max(home_xG_avg, away_xG_avg) > 0:
                        draw_factor = 1.0 - abs(home_xG_avg - away_xG_avg) / max(home_xG_avg, away_xG_avg)
                    else:
                        draw_factor = 1.0
                    prob_draw = min(0.4, max(0.1, draw_factor * 0.3))

                    total = prob_home + prob_draw + prob_away
                    prob_home /= total
                    prob_draw /= total
                    prob_away /= total

                    your_prob_home = round(prob_home * 100, 1)
                    your_prob_draw = round(prob_draw * 100, 1)
                    your_prob_away = round(prob_away * 100, 1)
            
            bookmaker_prob_home = round((1 / home_odds) * 100, 1)
            bookmaker_prob_draw = round((1 / draw_odds) * 100, 1)
            bookmaker_prob_away = round((1 / away_odds) * 100, 1)
            
            if your_prob_home is None:
                max_prob = max(bookmaker_prob_home, bookmaker_prob_draw, bookmaker_prob_away)
                prob_home, prob_draw, prob_away = bookmaker_prob_home, bookmaker_prob_draw, bookmaker_prob_away
                risk_level = "📊 По коэффициентам"
                bet_recommendation = ""
                if max_prob == prob_home:
                    bet_recommendation = f"Победа {home_team}"
                elif max_prob == prob_away:
                    bet_recommendation = f"Победа {away_team}"
                else:
                    bet_recommendation = "Ничья"
            else:
                prob_home, prob_draw, prob_away = your_prob_home, your_prob_draw, your_prob_away
                max_prob = max(prob_home, prob_draw, prob_away)
                
                value_bet = False
                if prob_home > bookmaker_prob_home + 10:
                    value_bet = True
                    bet_recommendation = f"Победа {home_team}"
                elif prob_away > bookmaker_prob_away + 10:
                    value_bet = True
                    bet_recommendation = f"Победа {away_team}"
                elif prob_draw > bookmaker_prob_draw + 10:
                    value_bet = True
                    bet_recommendation = "Ничья"
                else:
                    if max_prob == prob_home:
                        bet_recommendation = f"Победа {home_team}"
                    elif max_prob == prob_away:
                        bet_recommendation = f"Победа {away_team}"
                    else:
                        bet_recommendation = "Ничья"
                
                if value_bet:
                    risk_level = "💎 ЦЕННЫЙ ПРОГНОЗ"
                elif max_prob >= 65:
                    risk_level = "✅ ПОЛНЫЙ БАНК"
                elif max_prob >= 55:
                    risk_level = "🟢 СРЕДНИЙ БАНК"
                elif max_prob >= 50:
                    risk_level = "🟡 МАЛЫЙ БАНК"
                else:
                    risk_level = "🔴 НЕ СТАВИТЬ"
                    bet_recommendation = "Матч слишком рискованный"
            
            analysis = ""
            total_analysis = ""
            
            if home_stat and away_stat:
                matches_home = home_stat['wins'] + home_stat['draws'] + home_stat['loses']
                matches_away = away_stat['wins'] + away_stat['draws'] + away_stat['loses']
                home_xG_avg = round(home_stat['xG'] / matches_home, 2) if matches_home > 0 else 0
                away_xG_avg = round(away_stat['xG'] / matches_away, 2) if matches_away > 0 else 0
                home_xGA_avg = round(home_stat['xGA'] / matches_home, 2) if matches_home > 0 else 0
                away_xGA_avg = round(away_stat['xGA'] / matches_away, 2) if matches_away > 0 else 0
                
                if home_xG_avg > away_xG_avg:
                    analysis += f"\n📈 {home_team} имеет лучший xG ({home_xG_avg})"
                elif away_xG_avg > home_xG_avg:
                    analysis += f"\n📈 {away_team} имеет лучший xG ({away_xG_avg})"
                
                if home_xGA_avg < away_xGA_avg:
                    analysis += f"\n🛡️ {home_team} лучше защищается (xGA: {home_xGA_avg})"
                elif away_xGA_avg < home_xGA_avg:
                    analysis += f"\n🛡️ {away_team} лучше защищается (xGA: {away_xGA_avg})"
                
                point_diff = abs(home_stat['points'] - away_stat['points'])
                if home_stat['points'] > away_stat['points']:
                    analysis += f"\n📊 {home_team} опережает на {point_diff} очк."
                elif away_stat['points'] > home_stat['points']:
                    analysis += f"\n📊 {away_team} опережает на {point_diff} очк."
                
                total_xG = home_xG_avg + away_xG_avg
                if total_xG >= 2.8:
                    over_text = "🔥 Высокая (70%)"
                elif total_xG >= 2.5:
                    over_text = "📈 Средняя (60%)"
                elif total_xG >= 2.2:
                    over_text = "⚖️ Повышенная (50%)"
                else:
                    over_text = "📉 Низкая"

                if home_xG_avg >= 1.0 and away_xG_avg >= 1.0:
                    btts_text = "✅ Высокая (75%)"
                elif home_xG_avg >= 0.8 and away_xG_avg >= 0.8:
                    btts_text = "📊 Средняя (65%)"
                else:
                    btts_text = "❌ Низкая"

                total_analysis += f"\n📊 ТБ(2.5): {over_text} (xG: {total_xG})"
                total_analysis += f"\n⚽ Обе забьют: {btts_text}"
            
            message = (
                f"🔮 {league_name.upper()}\n"
                f"🏆 {home_team} – {away_team}\n\n"
                f"💰 Коэффициенты:\n"
                f"🏠 {home_odds} | 🤝 {draw_odds} | ✈️ {away_odds}\n\n"
            )
            
            if your_prob_home is not None:
                message += (
                    f"🤖 Наша модель:\n"
                    f"🏠 {prob_home}% | 🤝 {prob_draw}% | ✈️ {prob_away}%\n\n"
                )
            else:
                message += "⚠️ Наша модель: данные недоступны\n\n"
            
            message += (
                f"📊 Букмекер:\n"
                f"🏠 {bookmaker_prob_home}% | 🤝 {bookmaker_prob_draw}% | ✈️ {bookmaker_prob_away}%\n\n"
                f"{risk_level}\n"
                f"🎯 {bet_recommendation}"
                f"{analysis}"
                f"{total_analysis}\n\n"
                f"#Прогноз"
            )
            await query.edit_message_text(message)
            
        except Exception as e:
            await query.edit_message_text("❌ Ошибка обработки")

# === ОСТАЛЬНЫЕ КОМАНДЫ ===
async def live_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚡ LIVE АНАЛИЗ\n\n"
        "📝 Введите данные **строго в этом порядке**:\n\n"
        "1. Команды: Металлург – Амур\n"
        "2. Счёт: 2-1\n"
        "3. Минута: 81\n"
        "4. Удары в створ: 3-6\n"
        "5. Угловые: 3-5\n"
        "6. ЖК: 1-2\n"
        "7. КК: 0-0\n"
        "8. Владение: 35-65\n\n"
        "Минимум — первые 2 строки:\n"
        "Металлург – Амур\n"
        "2-1"
    )
    context.user_data['awaiting_live_stats'] = True

async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def publish_super_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Ищем ТОП-прогноз дня...")
    
    leagues = {39: "АПЛ", 140: "Ла Лига", 78: "Бундеслига", 135: "Серия А", 61: "Лига 1"}
    all_matches = {}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'X-API-Key': 'm75d5yyd3o97pntw'
    }
    
    for league_id, league_name in leagues.items():
        try:
            url = f"https://api.sstats.net/games/list?LeagueId={league_id}&Upcoming=true&Limit=5"
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                games = resp.json().get('data', [])
                for game in games:
                    game_id = game['id']
                    odds_list = game.get('odds', [])
                    home_odds = away_odds = draw_odds = None
                    for market in odds_list:
                        if market.get('marketId') == 1:
                            for odd in market.get('odds', []):
                                if odd['name'] == 'Home':
                                    home_odds = odd['value']
                                elif odd['name'] == 'Away':
                                    away_odds = odd['value']
                                elif odd['name'] == 'Draw':
                                    draw_odds = odd['value']
                    if home_odds is not None and away_odds is not None and draw_odds is not None:
                        all_matches[game_id] = {
                            'home': game['homeTeam']['name'],
                            'away': game['awayTeam']['name'],
                            'league': league_name,
                            'league_id': league_id,
                            'home_odds': home_odds,
                            'away_odds': away_odds,
                            'draw_odds': draw_odds
                        }
        except Exception as e:
            continue
    
    super_match = select_super_match(all_matches)
    teaser = generate_teaser_post(super_match)
    
    if teaser:
        try:
            await context.bot.send_message(
                chat_id=CHANNEL_ID,
                text=teaser,
                parse_mode='Markdown'
            )
            await update.message.reply_text("✅ ТОП-прогноз дня опубликован в канал!")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка публикации: убедитесь, что бот — админ канала.\n{e}")
    else:
        await update.message.reply_text("❌ Не удалось найти ни одного матча с коэффициентами.")

async def handle_live_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_live_stats'):
        return
    
    context.user_data['awaiting_live_stats'] = False
    stats_text = update.message.text.strip()
    live_stats = parse_live_stats(stats_text)
    
    if not live_stats or 'teams' not in live_stats:
        await update.message.reply_text(
            "❌ Не удалось распознать данные.\n\n"
            "📌 Пример правильного ввода:\n"
            "Металлург – Амур\n"
            "2-1\n"
            "81\n"
            "3-6\n"
            "3-5\n"
            "1-2\n"
            "0-0\n"
            "35-65"
        )
        return
    
    home_team, away_team = live_stats['teams']
    home_prob, away_prob = calculate_live_prediction(home_team, away_team, live_stats)
    
    minute = live_stats.get('minute', 45)
    goals = live_stats.get('goals', (0, 0))
    shots_on_target = live_stats.get('shots_on_target', (0, 0))
    corners = live_stats.get('corners', (0, 0))
    yellow_cards = live_stats.get('yellow_cards', (0, 0))
    red_cards = live_stats.get('red_cards', (0, 0))
    possession = live_stats.get('possession', (50, 50))
    
    message = f"⚡ LIVE АНАЛИЗ\n🏆 {home_team} – {away_team}\n⏱️ {minute} минута\n\n"
    message += f"⚽ Счёт: {goals[0]}-{goals[1]}\n"
    if shots_on_target != (0, 0):
        message += f"🎯 Удары в створ: {shots_on_target[0]}-{shots_on_target[1]}\n"
    if corners != (0, 0):
        message += f"🚩 Угловые: {corners[0]}-{corners[1]}\n"
    if yellow_cards != (0, 0) or red_cards != (0, 0):
        message += f"🟨 ЖК: {yellow_cards[0]}-{yellow_cards[1]} | 🔴 КК: {red_cards[0]}-{red_cards[1]}\n"
    if possession != (50, 50):
        message += f"⚽ Владение: {possession[0]}-{possession[1]}%\n"
    
    message += f"\n🎯 Вероятности победы:\n🏠 {home_prob}% | ✈️ {away_prob}%\n\n"
    
    if home_prob >= 65:
        message += "✅ ПОЛНЫЙ БАНК\n🎯 Победа " + home_team
    elif away_prob >= 65:
        message += "✅ ПОЛНЫЙ БАНК\n🎯 Победа " + away_team
    elif home_prob >= 55:
        message += "🟢 СРЕДНИЙ БАНК\n🎯 Победа " + home_team
    elif away_prob >= 55:
        message += "🟢 СРЕДНИЙ БАНК\n🎯 Победа " + away_team
    elif home_prob >= 50:
        message += "🟡 МАЛЫЙ БАНК\n🎯 Победа " + home_team
    elif away_prob >= 50:
        message += "🟡 МАЛЫЙ БАНК\n🎯 Победа " + away_team
    else:
        message += "🔴 НЕ СТАВИТЬ\nМатч слишком рискованный"
    
    message += "\n\n#LiveАнализ"
    await update.message.reply_text(message)

# === Запуск ===
def main():
    print("🚀 Запуск бота на Render.com...")
    download_understat_data()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("live", live_command))
    app.add_handler(CommandHandler("refresh", refresh))
    app.add_handler(CommandHandler("publish", publish_super_match))
    app.add_handler(CallbackQueryHandler(button_handler, pattern=r"^m_\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_live_stats))
    
    print("✅ Бот готов к работе!")
    app.run_polling()

if __name__ == "__main__":
    main()
