# -*- coding: utf-8 -*-
"""Локализация интерфейса: T("русский исходник") → строка текущего языка.

Ключ — русский текст прямо в коде (код остаётся читаемым), переводы — в
словарях ниже. Подстановки — через именованные поля: T("{n} мин", n=25).
Язык по умолчанию — английский; переключается в настройках.
"""
LANGUAGES = (("en", "English"), ("ru", "Русский"))

_lang = "en"


def set_language(lang: str) -> None:
    global _lang
    _lang = lang if lang in dict(LANGUAGES) else "en"


def language() -> str:
    return _lang


def T(text: str, **kw) -> str:
    if _lang == "en":
        text = EN.get(text, text)
    return text.format(**kw) if kw else text


def months_genitive() -> list:
    return MONTHS[_lang]


def weekdays_short() -> list:
    return WEEKDAYS_SHORT[_lang]


def weekdays_full() -> list:
    return WEEKDAYS_FULL[_lang]


MONTHS = {
    "ru": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
           "сентября", "октября", "ноября", "декабря"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
}
WEEKDAYS_SHORT = {
    "ru": ["пн", "вт", "ср", "чт", "пт", "сб", "вс"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
}
WEEKDAYS_FULL = {
    "ru": ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}

# Фразы для выхода из фокуса — вводятся на языке интерфейса.
PHRASES = {
    "ru": ["я выбираю отвлечься", "моё время дороже", "я возвращаюсь к работе позже",
           "лень платит копейками"],
    "en": ["i choose to get distracted", "my time is worth more", "i will get back to work later",
           "laziness pays pennies"],
}

EN = {
    # --- общее / трей / тосты
    "Фокус": "Focus",
    "Перерыв": "Break",
    "Длинный перерыв": "Long break",
    "готов к фокусу": "ready to focus",
    "Фокус — {left}  ({n} мин)": "Focus — {left}  ({n} min)",
    "Фокус до {until}  ({n} мин)": "Focus until {until}  ({n} min)",
    "{name} до {until}": "{name} until {until}",
    "Фокус завершён — самоотчёт…": "Focus finished — check-in…",
    "Начать фокус…": "Start focus…",
    "Завершить досрочно…": "End early…",
    "Пропустить перерыв": "Skip break",
    "Таймер на экране": "On-screen timer",
    "Статистика": "Statistics",
    "Фото по дням": "Photos by day",
    "Настройки": "Settings",
    "Выход": "Quit",
    "Скрыть таймер": "Hide timer",
    "нет прав администратора": "no administrator rights",
    "Блокировка сайтов, папок и приложений не будет работать. Запусти FocusShield от имени "
    "администратора.":
        "Blocking of websites, folders and apps won't work. Run FocusShield as administrator.",
    "Фокус восстановлен": "Focus restored",
    "Осталось {left}": "{left} left",
    "не удалось заблокировать": "blocking failed",
    "Нет прав на hosts-файл": "No permission to edit the hosts file",
    "Закрыто — ты в фокусе": "Closed — you're in focus",
    "отойди от экрана": "step away from the screen",
    "Готово": "Done",
    "Самоотчёт по сессии…": "Session check-in…",
    "Готов к фокусу — нажми ▶": "Ready to focus — press ▶",
    "Фокус: {n} мин": "Focus: {n} min",
    "Погнали": "Let's go",
    "Фокус прерван": "Focus ended early",
    "Блокировка снята": "Blocking is off",
    "Таймер скрыт": "Timer hidden",
    "Вернуть: трей → «Таймер на экране»": "Bring it back: tray → “On-screen timer”",
    "Настройки сохранены": "Settings saved",
    "Тема применится к новым окнам": "The theme applies to newly opened windows",
    "Фокус завершён — перерыв!": "Focus done — take a break!",
    "{n} мин без блокировки": "{n} min, blocking off",
    "Фокус завершён": "Focus finished",
    "Отдохни — и возвращайся": "Rest — then come back",
    "продолжение": "continued",
    "Снова фокус: {n} мин": "Back to focus: {n} min",
    "Перерыв закончен": "Break is over",
    "Начни следующую сессию из трея": "Start the next session from the tray",
    "Вкладка закрыта — ты в фокусе": "Tab closed — you're in focus",
    "Вернись к фокусу": "Back to focus",
    "Вернул: {title}": "Brought back: {title}",
    # --- блокировщик папок
    "папка не найдена": "folder not found",
    "это корень диска": "it's a drive root",
    "системная или служебная папка ({path})": "system or app folder ({path})",
    # --- новая сессия
    "Новая фокус-сессия": "New focus session",
    "Пока идёт сессия, сайты из списка блокировки недоступны.":
        "While the session runs, blocked websites are unavailable.",
    "Длительность": "Duration",
    "{n} мин": "{n} min",
    "или": "or",
    "мин": "min",
    "Намерение": "Intention",
    "Что конкретно будет готово к концу сессии?":
        "What exactly will be done by the end of the session?",
    "Хорошо: «дописать README и отправить PR». Плохо: «поработать».":
        "Good: “finish the README and open a PR”. Bad: “do some work”.",
    "Начать фокус": "Start focus",
    "Отмена": "Cancel",
    "Enter — начать · Shift+Enter — новая строка": "Enter — start · Shift+Enter — new line",
    # --- самоотчёт
    "Сессия завершена": "Session complete",
    "{a} из {p} мин в фокусе": "{a} of {p} min in focus",
    "Получилось?": "Did you make it?",
    "Да, сделал": "Yes, done",
    "Частично": "Partly",
    "Не вышло": "No",
    # --- выход из фокуса
    "Выйти из фокуса?": "Leave focus?",
    "Блокировка снимется, а сессия засчитается как прерванная.":
        "Blocking will be lifted and the session will count as ended early.",
    "Чтобы выйти, введи фразу:": "To leave, type this phrase:",
    "Остаться в фокусе": "Stay in focus",
    "Выйти": "Leave",
    "Кнопка «Выйти» станет доступна через {n} с": "“Leave” becomes available in {n} s",
    "Введи фразу точно как написано": "Type the phrase exactly as shown",
    "Можно выйти": "You can leave now",
    # --- перерыв
    "Блокировка снята. Отойди от экрана.": "Blocking is off. Step away from the screen.",
    "Другая практика": "Another practice",
    "осталось": "left",
    "вдох": "inhale",
    "задержка": "hold",
    "выдох": "exhale",
    "Дыхание 4-7-8": "4-7-8 breathing",
    "Вдох носом на 4 счёта, задержка на 7, медленный выдох ртом на 8. "
    "Следи за кругом — 3–4 цикла.":
        "Inhale through your nose for 4, hold for 7, exhale slowly through your mouth "
        "for 8. Follow the circle — 3–4 cycles.",
    "Глаза 20-20-20": "Eyes 20-20-20",
    "Посмотри на что-нибудь в 6 метрах, например за окно, 20 секунд. "
    "Несколько раз моргни.":
        "Look at something 20 feet (6 m) away, e.g. out the window, for 20 seconds. "
        "Blink a few times.",
    "Разминка": "Stretch",
    "Встань, потянись вверх, покрути плечами и шеей. Пройдись по комнате.":
        "Stand up, stretch upward, roll your shoulders and neck. Walk around the room.",
    "Вода": "Water",
    "Выпей стакан воды — обезвоживание первым бьёт по концентрации.":
        "Drink a glass of water — dehydration hits focus first.",
    # --- статистика
    "Сегодня": "Today",
    "Вчера": "Yesterday",
    "сегодня": "today",
    "Обзор": "Overview",
    "минут в фокусе сегодня": "minutes in focus today",
    "сессий сегодня": "sessions today",
    "дней подряд": "day streak",
    "отвлечений сегодня": "distractions today",
    "Последние 7 дней": "Last 7 days",
    "Намерения": "Intentions",
    "Когда": "When",
    "Мин": "Min",
    "Итог": "Outcome",
    "✓ сделано": "✓ done",
    "◐ частично": "◐ partly",
    "✕ не вышло": "✕ not done",
    "⏹ прервано": "⏹ ended early",
    "День": "Day",
    "Фото": "Photos",
    "Все фото": "All photos",
    "Открыть папку дня": "Open day folder",
    "Снимки делаются только во время фокус-сессий и хранятся только на этом "
    "компьютере. Удаляются автоматически через {n} дн.":
        "Captures are taken only during focus sessions and stay on this computer. "
        "They're deleted automatically after {n} days.",
    "Фото пока нет": "No photos yet",
    "Снимки появятся во время фокус-сессий, если камера или скриншоты включены в "
    "настройках.":
        "Captures appear during focus sessions if the camera or screenshots are "
        "enabled in Settings.",
    "{n} фото": "{n} photos",
    "файл повреждён": "file is damaged",
    "камера": "camera",
    "экран": "screen",
    # --- настройки
    "Сохранить": "Save",
    "Язык": "Language",
    "Применится к окнам, открытым после сохранения.":
        "Applies to windows opened after saving.",
    "Плавающее окно поверх всех окон: время, намерение и кнопки. Перетаскивается "
    "мышью, правый клик — меню.":
        "A floating window on top of everything: time, intention and buttons. "
        "Drag it with the mouse, right-click for the menu.",
    "Всегда": "Always",
    "Только во время сессии и перерыва": "Only during sessions and breaks",
    "Не показывать": "Don't show",
    "Помодоро": "Pomodoro",
    "Короткий перерыв": "Short break",
    "Длинный перерыв после": "Long break after",
    "фокусов": "sessions",
    "Автопродолжение": "Auto-continue",
    "Перерыв и следующий фокус начинаются сами.":
        "Breaks and the next focus session start automatically.",
    "Строгий режим": "Strict mode",
    "Выйти из фокуса досрочно можно только подождав 10 секунд и введя фразу.":
        "Leaving focus early requires waiting 10 seconds and typing a phrase.",
    "Блокировка сайтов": "Website blocking",
    "Один домен в строке, действует только во время фокуса. Поддомены пишутся "
    "отдельно: youtube.com и www.youtube.com.":
        "One domain per line, active only during focus. List subdomains separately: "
        "youtube.com and www.youtube.com.",
    "Вернуть стандартный список": "Restore default list",
    "Блокировать DoH-серверы": "Block DoH servers",
    "Чтобы «безопасный DNS» браузера не обходил блокировку.":
        "So the browser's “secure DNS” can't bypass blocking.",
    "Страж вкладок": "Tab guard",
    "Блокировка через hosts не действует, если браузер ходит через прокси или VPN "
    "(например, v2rayN). Страж смотрит на заголовок вкладки и закрывает её, если в "
    "нём есть одно из слов ниже.":
        "Hosts-based blocking doesn't work when the browser uses a proxy or VPN "
        "(e.g. v2rayN). The guard watches tab titles and closes a tab if its title "
        "contains one of the words below.",
    "Закрывать такие вкладки во время фокуса": "Close such tabs during focus",
    "Слова в заголовке вкладки, по одному в строке:": "Tab title words, one per line:",
    "Запрет приложений и папок": "Blocked apps and folders",
    "Во время фокуса запрещённые приложения закрываются, а запрещённые папки не "
    "открываются — ни в Проводнике, ни в других программах. После сессии всё снова "
    "доступно.":
        "During focus, blocked apps are closed and blocked folders can't be opened — "
        "neither in File Explorer nor in other programs. Everything is available "
        "again after the session.",
    "Приложения (имя exe, по одному в строке):": "Apps (exe name, one per line):",
    "Из запущенных:": "From running:",
    "Добавить": "Add",
    "Папки (полный путь, по одной в строке):": "Folders (full path, one per line):",
    "Выбрать папку…": "Choose folder…",
    "Папка, запрещённая во время фокуса": "Folder blocked during focus",
    "Нельзя заблокировать {path}: {reason}": "Can't block {path}: {reason}",
    "Фокус-приложения": "Focus apps",
    "Во время фокуса FocusShield возвращает тебя к выбранным приложениям.":
        "During focus, FocusShield brings you back to the selected apps.",
    "Когда возвращать:": "Bring back when:",
    "Приложение свёрнуто": "The app is minimized",
    "Приложение не на переднем плане (ушёл в другое окно)":
        "The app isn't in the foreground (you switched to another window)",
    "В обоих случаях": "In both cases",
    "Через": "After",
    "сек": "sec",
    "Открытые сейчас приложения:": "Currently open apps:",
    "Обновить": "Refresh",
    "Другие (имя exe, по одному в строке):": "Others (exe name, one per line):",
    "Снимки": "Captures",
    "Только во время фокуса, хранятся только на этом компьютере, в папках по дням.":
        "Only during focus, stored only on this computer, in folders by day.",
    "Фото с веб-камеры": "Webcam photos",
    "Скриншоты экрана": "Screenshots",
    "Раз в": "Every",
    "Хранить": "Keep for",
    "дней": "days",
    "Открыть папку с фото": "Open photos folder",
    "Оформление": "Appearance",
    "Как в Windows": "Same as Windows",
    "Светлая": "Light",
    "Тёмная": "Dark",
}
