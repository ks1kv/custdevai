/**
 * Локализация интерфейса (NFR-OPS-06: только русский язык в текущей версии).
 */

export const t = {
  app: {
    title: "CustDevAI",
    subtitle: "Панель управления исследованиями",
  },
  nav: {
    dashboard: "Дашборд",
    scripts: "Сценарии",
    campaigns: "Кампании",
    archive: "Архив",
    compare: "Сравнение",
    settings: "Настройки",
    logout: "Выйти",
  },
  login: {
    title: "Вход в панель",
    email: "Email",
    password: "Пароль",
    submit: "Войти",
    errorCredentials: "Неверный email или пароль.",
    errorRateLimit:
      "Слишком много неудачных попыток. Подождите 15 минут и попробуйте снова.",
  },
  dashboard: {
    title: "Кампании",
    create: "Создать кампанию",
    empty: "Кампаний пока нет. Запустите первую через мастер.",
    wizard: "Мастер первой кампании",
  },
  campaign: {
    status: {
      draft: "Черновик",
      running: "Активна",
      paused: "Пауза",
      completed: "Завершена",
    },
    analysisStatus: {
      pending: "Анализ не запущен",
      running: "Анализ выполняется",
      completed: "Анализ завершён",
      failed: "Ошибка анализа",
    },
    tabs: {
      overview: "Обзор",
      transcripts: "Транскрипты",
      sentiment: "Тональность",
      topics: "Темы",
      reports: "Отчёты",
    },
    runAnalysis: "Запустить ML-анализ",
    targetTopicCount: "Целевое число тем (3–20)",
    sessionsCount: "Сессий",
    sessionsCompleted: "Завершено",
    sessionsInterrupted: "Прервано",
  },
  reports: {
    title: "Отчёты по кампании",
    generatePdf: "Сгенерировать PDF",
    generateXlsx: "Сгенерировать XLSX",
    download: "Скачать",
    generatedAt: "Сгенерирован",
    size: "Размер",
    notReady:
      "Отчёт станет доступен после завершения ML-анализа. Запустите анализ во вкладке «Обзор».",
    empty: "Отчёты ещё не сгенерированы. Нажмите кнопку выше.",
  },
  wizard: {
    title: "Мастер первой кампании",
    step1: "Шаг 1: создайте сценарий",
    step2: "Шаг 2: добавьте вопросы",
    step3: "Шаг 3: запустите кампанию",
    step4: "Готово",
    next: "Далее",
    back: "Назад",
    finish: "Завершить",
  },
  settings: {
    title: "Настройки профиля",
    fullName: "Имя и фамилия",
    email: "Email (нельзя изменить)",
    telegramChatId: "Telegram chat_id для push-уведомлений",
    telegramHelp:
      "Узнайте свой chat_id у @userinfobot в Telegram и впишите сюда. " +
      "После этого второй push «ML-анализ завершён» будет приходить вам напрямую.",
    save: "Сохранить",
    saved: "Сохранено",
  },
  errors: {
    generic: "Произошла ошибка. Попробуйте ещё раз.",
    network: "Не удалось связаться с сервером.",
    forbidden: "Недостаточно прав для выполнения операции.",
    notFound: "Запрашиваемый ресурс не найден.",
  },
  common: {
    loading: "Загрузка…",
    save: "Сохранить",
    cancel: "Отмена",
    confirm: "Подтвердить",
    delete: "Удалить",
    yes: "Да",
    no: "Нет",
  },
} as const;
