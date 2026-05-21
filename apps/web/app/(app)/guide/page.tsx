"use client";

// /guide — руководство менеджера по работе с CRM.
// Нативная страница в дизайн-системе приложения (brand-токены, светлая тема).
// Содержание выверено по реальному коду: 12 этапов дефолтной воронки,
// гейт «экономический покупатель» с этапа Multi-stakeholder, реальная
// терминология навигации. Источник прозы — docs/manual/РУКОВОДСТВО-МЕНЕДЖЕРА.md.

import { useState } from "react";
import {
  CalendarDays,
  Kanban,
  Target,
  Bot,
  CheckSquare,
  Users,
  MessageCircle,
  Search,
  Bell,
  Settings,
  LogIn,
  HelpCircle,
  Sparkles,
  AlertTriangle,
  Info,
  Lightbulb,
  CheckCircle2,
  ChevronDown,
  FileText,
  type LucideIcon,
} from "lucide-react";

// ─── Данные ──────────────────────────────────────────────────────

const TOC: { id: string; label: string; icon: LucideIcon }[] = [
  { id: "start", label: "Начало работы", icon: HelpCircle },
  { id: "login", label: "Вход в систему", icon: LogIn },
  { id: "today", label: "Рабочий стол «Сегодня»", icon: CalendarDays },
  { id: "pipeline", label: "Воронка продаж", icon: Kanban },
  { id: "leadcard", label: "Карточка лида", icon: Target },
  { id: "pool", label: "База лидов (пул)", icon: Target },
  { id: "blake", label: "Блейк — AI-помощник", icon: Bot },
  { id: "tasks", label: "Задачи", icon: CheckSquare },
  { id: "notes", label: "Заметки", icon: FileText },
  { id: "contacts", label: "Контакты и компании", icon: Users },
  { id: "inbox", label: "Мессенджеры и звонки", icon: MessageCircle },
  { id: "search", label: "Поиск", icon: Search },
  { id: "notifications", label: "Уведомления", icon: Bell },
  { id: "profile", label: "Настройки профиля", icon: Settings },
  { id: "faq", label: "Частые вопросы", icon: HelpCircle },
];

// Реальные 12 этапов дефолтной воронки (apps/api/app/pipelines/models.py).
const STAGES: { name: string; color: string }[] = [
  { name: "Новый контакт", color: "#a1a1a6" },
  { name: "Квалификация", color: "#0a84ff" },
  { name: "Discovery", color: "#5e5ce6" },
  { name: "Solution Fit", color: "#bf5af2" },
  { name: "Business Case / КП", color: "#ff9f0a" },
  { name: "Multi-stakeholder", color: "#ff6b00" },
  { name: "Договор / пилот", color: "#ff3b30" },
  { name: "Производство", color: "#ff2d55" },
  { name: "Пилот", color: "#34c759" },
  { name: "Scale / серия", color: "#30d158" },
  { name: "Закрыто (won) ✅", color: "#32d74b" },
  { name: "Закрыто (lost) ❌", color: "#ef4444" },
];

const GLOSSARY: { term: string; def: string }[] = [
  { term: "Лид", def: "Потенциальный клиент: компания + контакты + сделка. Главный объект работы." },
  { term: "Воронка", def: "12 этапов сделки — от «Новый контакт» до «Закрыто (won/lost)»." },
  { term: "Fit-score", def: "Оценка AI (0–10): насколько лид подходит под идеального клиента. Видна в базе лидов." },
  { term: "Задача", def: "Дело по клиенту со сроком и галочкой. Ставит менеджер вручную в карточке лида." },
  { term: "Заметка", def: "Свободное наблюдение о клиенте. Не задача — без срока и галочки." },
  { term: "Гейт", def: "Условие перехода на следующий этап. Не выполнено — система не пустит." },
  { term: "Rotting", def: "«Подвисший» лид — давно без активности. Требует внимания." },
  { term: "Пул (База лидов)", def: "Общий список неназначенных лидов — берите новых клиентов отсюда." },
];

const FAQ: { q: string; a: string }[] = [
  {
    q: "Не вижу разделы «Формы», «Автоматизации» или «Журнал»",
    a: "Эти разделы доступны только руководителям (admin/head) или администратору. Это нормально для роли менеджера. Пункт «Команда» у менеджера ведёт в раздел настроек.",
  },
  {
    q: "Не могу перевести лид на следующий этап",
    a: "Скорее всего, не выполнено условие этапа (гейт). Частый случай — начиная с этапа «Multi-stakeholder» нужен контакт с ролью «Экономический покупатель» (ЛПР). Откройте карточку лида → «Контакты» → добавьте контакт с этой ролью → повторите перевод. Если гейт мягкий, система попросит указать причину пропуска.",
  },
  {
    q: "Как поставить задачу?",
    a: "Задача всегда привязана к клиенту. Откройте карточку лида → вкладка «Задачи» → «Добавить задачу»: впишите текст и срок. Задача появится в списке на «Сегодня» и на странице «Задачи». Отдельных задач без клиента пока нет — это появится позже.",
  },
  {
    q: "Где вести заметки о клиенте?",
    a: "В карточке лида → вкладка «Заметки». Это свободные наблюдения (без срока и галочки). Заметки видны всей команде, показывают автора и сохраняются при передаче лида. Редактировать и удалять может автор или администратор.",
  },
  {
    q: "AI-бриф пустой или обогащение «крутится»",
    a: "Обогащение идёт в фоне и занимает несколько секунд. Если зависло надолго — обновите страницу и запустите обогащение ещё раз из карточки лида (вкладка «Сделка и AI»).",
  },
  {
    q: "Взял не тот лид из базы",
    a: "Нажмите «Вернуть в пул» в карточке лида — он снова станет доступен всей команде.",
  },
  {
    q: "Блейк дал неточный совет",
    a: "Блейк — помощник, а не автопилот. Он не ставит и не приоритизирует ваши задачи — это делаете только вы. Используйте его подсказки как отправную точку и проверяйте их в контексте сделки.",
  },
  {
    q: "Входящее сообщение не привязалось к лиду",
    a: "Откройте раздел «Мессенджеры» → триаж несматченных. Найдите сообщение и вручную привяжите к нужному лиду. Так бывает, если клиент написал с нового номера или почты, которых нет в CRM.",
  },
];

// ─── Переиспользуемые блоки ──────────────────────────────────────

function Section({ id, icon: Icon, title, kicker, children }: {
  id: string; icon: LucideIcon; title: string; kicker: string; children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-[128px] mb-12">
      <div className="mb-5">
        <div className="flex items-center gap-2 text-brand-accent mb-2">
          <Icon size={16} />
          <span className="type-caption text-brand-accent">{kicker}</span>
        </div>
        <h2 className="type-section-title text-brand-primary">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function Card({ title, icon: Icon, children, className = "" }: {
  title?: string; icon?: LucideIcon; children: React.ReactNode; className?: string;
}) {
  return (
    <div className={`bg-white border border-brand-border rounded-[2rem] p-6 ${className}`}>
      {title && (
        <div className="flex items-center gap-2.5 mb-3">
          {Icon && (
            <span className="w-8 h-8 rounded-full bg-brand-soft flex items-center justify-center shrink-0">
              <Icon size={16} className="text-brand-accent" />
            </span>
          )}
          <h3 className="type-card-title text-brand-primary">{title}</h3>
        </div>
      )}
      {children}
    </div>
  );
}

const ALERT_STYLES = {
  info: { bg: "bg-blue-50 border-blue-200", text: "text-blue-900", icon: Info, ic: "text-blue-500" },
  warn: { bg: "bg-amber-50 border-amber-200", text: "text-amber-900", icon: AlertTriangle, ic: "text-amber-500" },
  success: { bg: "bg-emerald-50 border-emerald-200", text: "text-emerald-900", icon: CheckCircle2, ic: "text-emerald-500" },
  tip: { bg: "bg-brand-soft border-brand-accent/20", text: "text-brand-muted-strong", icon: Lightbulb, ic: "text-brand-accent" },
} as const;

function Alert({ kind, children }: { kind: keyof typeof ALERT_STYLES; children: React.ReactNode }) {
  const s = ALERT_STYLES[kind];
  const Icon = s.icon;
  return (
    <div className={`flex gap-3 items-start border rounded-2xl px-4 py-3.5 my-4 ${s.bg} ${s.text}`}>
      <Icon size={18} className={`shrink-0 mt-0.5 ${s.ic}`} />
      <div className="type-body">{children}</div>
    </div>
  );
}

function KV({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <ul className="divide-y divide-brand-border">
      {items.map(([k, v], i) => (
        <li key={i} className="flex flex-col sm:flex-row gap-1 sm:gap-4 py-2.5">
          <span className="type-label text-brand-primary sm:min-w-[180px] shrink-0">{k}</span>
          <span className="type-body text-brand-muted-strong">{v}</span>
        </li>
      ))}
    </ul>
  );
}

function Steps({ items }: { items: [string, string][] }) {
  return (
    <ol className="space-y-3.5">
      {items.map(([t, d], i) => (
        <li key={i} className="flex gap-3.5 items-start">
          <span className="w-7 h-7 rounded-full bg-brand-accent text-white type-button flex items-center justify-center shrink-0">
            {i + 1}
          </span>
          <div className="pt-0.5">
            <div className="type-label text-brand-primary">{t}</div>
            <div className="type-body text-brand-muted-strong">{d}</div>
          </div>
        </li>
      ))}
    </ol>
  );
}

// ─── Страница ────────────────────────────────────────────────────

export default function GuidePage() {
  const [openFaq, setOpenFaq] = useState<number | null>(0);

  return (
    <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-10 lg:py-12">
      {/* Hero */}
      <div className="bg-brand-dark text-white rounded-[2rem] p-8 sm:p-10 mb-8 relative overflow-hidden">
        <div className="absolute -top-16 -right-16 w-64 h-64 rounded-full bg-brand-accent/20 blur-3xl pointer-events-none" />
        <div className="relative">
          <div className="inline-flex items-center gap-1.5 bg-white/10 text-white/90 type-caption px-3 py-1 rounded-full mb-4">
            <Sparkles size={13} /> Руководство
          </div>
          <h1 className="type-page-title mb-3">Как работать с DrinkX CRM</h1>
          <p className="type-body text-white/70 max-w-xl">
            Всё для ежедневной работы: как вести сделки, находить новых клиентов и
            использовать AI-помощника Блейка. Технические детали не нужны — просто следуйте шагам.
          </p>
        </div>
      </div>

      <div className="grid lg:grid-cols-[220px_1fr] gap-8">
        {/* Оглавление */}
        <nav className="hidden lg:block">
          <div className="sticky top-[128px] space-y-0.5">
            {TOC.map(({ id, label, icon: Icon }) => (
              <a
                key={id}
                href={`#${id}`}
                className="flex items-center gap-2.5 px-3 py-2 rounded-full type-label text-brand-muted-strong hover:bg-brand-panel transition-colors"
              >
                <Icon size={15} className="text-brand-muted shrink-0" />
                {label}
              </a>
            ))}
          </div>
        </nav>

        {/* Контент */}
        <div className="min-w-0">
          {/* НАЧАЛО */}
          <Section id="start" icon={HelpCircle} kicker="Добро пожаловать" title="Ключевые понятия">
            <div className="grid sm:grid-cols-2 gap-3">
              {GLOSSARY.map((g) => (
                <div key={g.term} className="bg-white border border-brand-border rounded-2xl p-4">
                  <div className="type-label text-brand-primary mb-1">{g.term}</div>
                  <div className="type-body text-brand-muted-strong">{g.def}</div>
                </div>
              ))}
            </div>
            <Card title="Типичное утро менеджера" icon={CalendarDays} className="mt-4">
              <Steps
                items={[
                  ["Открыть «Сегодня»", "Главная страница после входа."],
                  ["Пройтись по списку задач", "Ваши задачи по клиентам, по сроку — ближайшие сверху."],
                  ["Отметить выполненное галочкой", "Прямо в виджете, не заходя в карточку."],
                  ["Заглянуть в «Устаревает»", "Клиенты без движения — чтобы никого не потерять."],
                ]}
              />
            </Card>
            <Alert kind="info">
              Часть разделов видна только руководителям («Формы», «Автоматизации», «Журнал»). Это
              нормально для роли менеджера — обратитесь к администратору, если нужен доступ.
            </Alert>
          </Section>

          {/* ВХОД */}
          <Section id="login" icon={LogIn} kicker="Доступ" title="Вход в систему">
            <div className="grid sm:grid-cols-3 gap-3">
              <Card title="Google"><p className="type-body text-brand-muted-strong">Вход через рабочий Google-аккаунт — самый удобный вариант.</p></Card>
              <Card title="Email"><p className="type-body text-brand-muted-strong">Введите почту — придёт ссылка-вход (magic-link), без пароля.</p></Card>
              <Card title="Тестовый вход"><p className="type-body text-brand-muted-strong">Кнопка для демо и обучения, если включена администратором.</p></Card>
            </div>
          </Section>

          {/* СЕГОДНЯ */}
          <Section id="today" icon={CalendarDays} kicker="Ежедневная работа" title="Рабочий стол «Сегодня»">
            <p className="type-body text-brand-muted-strong mb-3">
              Главный экран дня. Виджеты можно перетаскивать под себя — порядок запоминается.
            </p>
            <Alert kind="info">
              <strong>Список задач — это ваши собственные задачи по клиентам.</strong> Никакого AI:
              что вписали и на какой срок — то и видите. Отмечайте выполненное галочкой прямо здесь.
            </Alert>
            <Card>
              <KV items={[
                ["Список задач", "Ваши задачи по клиентам: галочка «выполнено», прогресс X/Y, фильтры (все / сегодня / просрочено), «Все задачи ↗»."],
                ["Напоминания", "Личные заметки-стикеры, без привязки к клиенту. Добавил — удалил."],
                ["Устаревает", "Клиенты без движения — займитесь ими в первую очередь."],
                ["В воронке", "Сколько у вас активных лидов в работе."],
                ["Стадии воронки", "Распределение ваших лидов по этапам."],
                ["Уведомления", "Что произошло сегодня."],
              ]} />
            </Card>
          </Section>

          {/* ВОРОНКА */}
          <Section id="pipeline" icon={Kanban} kicker="Продажи" title="Воронка продаж">
            <p className="type-body text-brand-muted-strong mb-3">
              Kanban-доска с колонками-этапами. Каждая карточка — один лид. Перетаскивайте карточки
              между этапами. На телефоне — список с лентой этапов сверху.
            </p>
            <Card title="Этапы дефолтной воронки (12)">
              <div className="flex flex-wrap gap-2">
                {STAGES.map((s) => (
                  <span key={s.name} className="inline-flex items-center gap-1.5 bg-brand-panel border border-brand-border rounded-full px-3 py-1.5 type-label text-brand-muted-strong">
                    <span className="w-2 h-2 rounded-full" style={{ background: s.color }} />
                    {s.name}
                  </span>
                ))}
              </div>
              <p className="type-hint text-brand-muted mt-3">Набор и критерии этапов настраивает администратор — у вашего workspace они могут отличаться.</p>
            </Card>
            <Alert kind="warn">
              <strong>Гейты.</strong> На некоторые этапы система не пустит без ключевой информации.
              Например, начиная с этапа <strong>«Multi-stakeholder»</strong> нужен контакт с ролью
              «Экономический покупатель» (ЛПР). У каждого этапа — свой набор критериев.
            </Alert>
            <Card className="mt-2">
              <KV items={[
                ["Видимость", "Менеджер видит своих лидов; руководитель (admin/head) — лидов всей команды."],
                ["Финальные этапы", "«Закрыто (won)» и «Закрыто (lost)» фиксируют дату закрытия."],
                ["Мягкий гейт", "Некоторые условия можно пропустить, указав причину."],
              ]} />
            </Card>
          </Section>

          {/* КАРТОЧКА */}
          <Section id="leadcard" icon={Target} kicker="Лиды" title="Карточка лида">
            <p className="type-body text-brand-muted-strong mb-3">
              Открывается кликом по лиду. Здесь вся информация и вся работа по клиенту.
            </p>
            <p className="type-caption text-brand-muted mb-3">Вкладки карточки:</p>
            <div className="grid sm:grid-cols-2 gap-3 mb-4">
              <Card title="Активность" icon={MessageCircle}><p className="type-body text-brand-muted-strong">Единая лента: комментарии, письма, звонки, изменения этапа, ответы Блейка. Спросить Блейка — написав в ленте «@Блейк …».</p></Card>
              <Card title="Сделка и AI" icon={Sparkles}><p className="type-body text-brand-muted-strong">Сумма, оборудование, количество + AI-бриф: автоматически собранные данные о компании.</p></Card>
              <Card title="Контакты" icon={Users}><p className="type-body text-brand-muted-strong">Люди со стороны клиента с ролями: ЛПР, чемпион, технический, операционный.</p></Card>
              <Card title="Задачи" icon={CheckSquare}><p className="type-body text-brand-muted-strong">Ваши задачи по этому клиенту: текст, срок, галочка. Ставите вы — без AI.</p></Card>
              <Card title="Заметки" icon={FileText}><p className="type-body text-brand-muted-strong">Свободные наблюдения о клиенте. С автором и датой, переживают передачу лида.</p></Card>
            </div>
            <Alert kind="info">
              <strong>Полоса этапов</strong> вверху карточки показывает текущий этап и сколько дней лид
              на нём. Свёрнута до соседних этапов — нажмите «показать все этапы», чтобы развернуть весь путь.
            </Alert>
            <Card title="Что можно делать">
              <Steps items={[
                ["Перевести лид на другой этап", "Система проверит гейты и зафиксирует переход."],
                ["Поставить задачу", "Вкладка «Задачи» — текст + срок. Появится и в списке на «Сегодня»."],
                ["Написать заметку", "Вкладка «Заметки» — наблюдение о клиенте."],
                ["Запустить AI-обогащение", "Вкладка «Сделка и AI» — соберёт данные о компании из открытых источников."],
                ["Спросить Блейка", "В ленте «Активность» напишите «@Блейк …» — совет по сделке, работа с возражениями."],
              ]} />
            </Card>
          </Section>

          {/* ПУЛ */}
          <Section id="pool" icon={Target} kicker="Новые клиенты" title="База лидов (пул)">
            <p className="type-body text-brand-muted-strong mb-3">
              В сайдбаре — пункт <strong>«База лидов»</strong>. Это общий банк неназначенных лидов,
              отсюда берут новых клиентов.
            </p>
            <Alert kind="info">
              <strong>Лиды отсортированы по Fit-score</strong> — сверху самые подходящие. Чем выше
              оценка AI, тем больше шансов на сделку.
            </Alert>
            <Card>
              <Steps items={[
                ["Фильтрация", "По городу, сегменту, приоритету — найдите подходящих."],
                ["Кнопка «Взять»", "Лид закрепится за вами и появится в вашей воронке."],
                ["Sprint-набор", "Можно взять сразу несколько лидов одним действием."],
              ]} />
            </Card>
            <Alert kind="warn">
              <strong>Правило:</strong> взяли — ведите. Не подходит — верните в пул, чтобы коллега мог взять.
            </Alert>
          </Section>

          {/* БЛЕЙК */}
          <Section id="blake" icon={Bot} kicker="AI-помощник" title="Блейк — ваш AI-помощник">
            <p className="type-body text-brand-muted-strong mb-3">
              AI-коуч по продажам. Живёт прямо в ленте <strong>«Активность»</strong> карточки лида —
              напишите в ленте <strong>«@Блейк …»</strong> и он ответит там же. Знает контекст сделки:
              этап, контакты, AI-бриф, базу знаний DrinkX.
            </p>
            <Card title="Что спросить у Блейка">
              <ul className="space-y-2 type-body text-brand-muted-strong list-none">
                <li>🎯 «Подготовь меня к звонку с этим клиентом»</li>
                <li>🛡 «Клиент говорит, что дорого. Как ответить?»</li>
                <li>📝 «Набросай черновик коммерческого предложения»</li>
                <li>📊 «Какие сигналы роста есть у этой компании?»</li>
              </ul>
            </Card>
            <Alert kind="tip">
              <strong>Важно:</strong> Блейк только советует — решение всегда за вами. Он
              <strong> не ставит и не приоритизирует ваши задачи</strong> и ничего не отправляет
              клиенту сам.
            </Alert>
          </Section>

          {/* ЗАДАЧИ */}
          <Section id="tasks" icon={CheckSquare} kicker="Планирование" title="Задачи">
            <Alert kind="info">
              <strong>Задачи ставите только вы, вручную, и всегда по конкретному клиенту.</strong>
              Никакой AI: ни ранжирования, ни автосоздания. Текст и срок задаёте сами.
            </Alert>
            <Card title="Как это работает">
              <KV items={[
                ["Где создать", "В карточке лида → вкладка «Задачи» → «Добавить задачу» (текст + срок)."],
                ["Где смотреть", "Список на «Сегодня» и полная страница «Задачи» (кнопка «Все задачи ↗»)."],
                ["Каждая задача", "Текст, срок (ваш) и галочка «выполнено». Просроченные подсвечены."],
                ["Фильтры на странице «Задачи»", "По статусу (открытые / выполненные / просрочено), сроку и поиск по клиенту."],
              ]} />
            </Card>
            <Alert kind="tip">
              Задача всегда привязана к клиенту. Отдельные задачи «без клиента» появятся позже —
              это отдельная функция следующего этапа.
            </Alert>
          </Section>

          {/* ЗАМЕТКИ */}
          <Section id="notes" icon={FileText} kicker="Клиент" title="Заметки">
            <p className="type-body text-brand-muted-strong mb-3">
              Свободные наблюдения о клиенте — в карточке лида, вкладка <strong>«Заметки»</strong>.
              Это не задачи (нет срока и галочки) и не лента активности.
            </p>
            <Card>
              <KV items={[
                ["Что писать", "Любые наблюдения: контекст, договорённости, особенности клиента."],
                ["Автор и дата", "У каждой заметки видно, кто и когда её написал."],
                ["При передаче лида", "Заметки остаются на клиенте и сохраняют автора."],
                ["Правка и удаление", "Может только автор заметки или администратор."],
              ]} />
            </Card>
          </Section>

          {/* КОНТАКТЫ */}
          <Section id="contacts" icon={Users} kicker="Клиентская база" title="Контакты и компании">
            <Card title="Контакты" icon={Users} className="mb-3">
              <KV items={[
                ["Где живут", "Внутри карточки лида — не отдельный раздел."],
                ["Роли", "ЛПР (экономический покупатель), чемпион, технический, операционный."],
                ["⚠️ Важно", "Укажите роль «Экономический покупатель» для ЛПР — без него не пройти гейты поздних этапов."],
              ]} />
            </Card>
            <Card title="Компании" icon={Users}>
              <KV items={[
                ["Карточка компании", "Все её лиды, контакты и недавняя активность в одном месте."],
                ["Дубли", "Система предупреждает при создании — проверьте, нет ли уже такой компании."],
                ["Удаление", "Компании не удаляются, а архивируются — история сохраняется."],
              ]} />
            </Card>
          </Section>

          {/* МЕССЕНДЖЕРЫ */}
          <Section id="inbox" icon={MessageCircle} kicker="Коммуникации" title="Мессенджеры и звонки">
            <p className="type-body text-brand-muted-strong mb-3">
              CRM подтягивает переписку из Gmail, Telegram, MAX и звонки телефонии. Раздел в сайдбаре — <strong>«Мессенджеры»</strong>.
            </p>
            <div className="grid sm:grid-cols-2 gap-3 mb-4">
              <Card title="Клиент узнан" icon={CheckCircle2} className="border-l-4 !border-l-emerald-400">
                <p className="type-body text-brand-muted-strong">Сообщение попадает прямо в ленту нужного лида — делать ничего не нужно.</p>
              </Card>
              <Card title="Клиент не узнан" icon={AlertTriangle} className="border-l-4 !border-l-amber-400">
                <p className="type-body text-brand-muted-strong">Сообщение уходит в триаж. Зайдите и вручную привяжите к нужному лиду.</p>
              </Card>
            </div>
            <Card>
              <KV items={[
                ["Отправить сообщение", "Из карточки лида — в любой подключённый канал."],
                ["Позвонить", "Клик-звонок из карточки без ручного набора."],
                ["Расшифровка звонков", "Звонки транскрибируются, к ним добавляется краткое содержание."],
              ]} />
            </Card>
            <Alert kind="tip"><strong>Совет:</strong> регулярно заглядывайте в триаж, чтобы ни одно обращение не потерялось.</Alert>
          </Section>

          {/* ПОИСК */}
          <Section id="search" icon={Search} kicker="Навигация" title="Глобальный поиск">
            <Card className="text-center py-8">
              <div className="flex items-center justify-center gap-2 mb-3">
                <kbd className="inline-flex items-center bg-brand-dark text-white rounded-lg px-3 py-1.5 font-mono text-md">⌘ Cmd</kbd>
                <span className="text-brand-muted text-lg">+</span>
                <kbd className="inline-flex items-center bg-brand-dark text-white rounded-lg px-3 py-1.5 font-mono text-md">K</kbd>
              </div>
              <p className="type-body text-brand-muted-strong">Или иконка поиска вверху. Ищет по компаниям, лидам и контактам.</p>
            </Card>
            <Alert kind="info">С <strong>3 символов</strong> работает умный поиск с опечатками — «Мкдоналдс» найдёт «Макдоналдс».</Alert>
          </Section>

          {/* УВЕДОМЛЕНИЯ */}
          <Section id="notifications" icon={Bell} kicker="Система" title="Уведомления">
            <Card title="Что приходит" className="mb-3">
              <ul className="space-y-1.5 type-body text-brand-muted-strong list-none">
                <li>📥 Передача лида вам от коллеги</li>
                <li>🤖 Готовность AI-обогащения</li>
                <li>✉️ Новое сообщение от клиента</li>
              </ul>
            </Card>
            <Card>
              <KV items={[
                ["«Прочитать»", "Отметить прочитанным, оставив в списке."],
                ["«Скрыть»", "Убрать из списка совсем."],
                ["Дедупликация", "Одинаковые уведомления не повторяются чаще раза в час."],
              ]} />
            </Card>
          </Section>

          {/* ПРОФИЛЬ */}
          <Section id="profile" icon={Settings} kicker="Профиль" title="Личные настройки">
            <Card>
              <KV items={[
                ["Имя и фото", "Отображается в ленте активности, заметках и при передаче лидов."],
                ["Часовой пояс", "Влияет на время уведомлений."],
                ["Специализация", "Сегменты, с которыми работаете — влияет на релевантность рекомендаций Блейка."],
                ["Оформление", "Светлая или тёмная тема интерфейса."],
              ]} />
            </Card>
          </Section>

          {/* FAQ */}
          <Section id="faq" icon={HelpCircle} kicker="Справка" title="Частые вопросы">
            <div className="space-y-2.5">
              {FAQ.map((item, i) => {
                const open = openFaq === i;
                return (
                  <div key={i} className="bg-white border border-brand-border rounded-2xl overflow-hidden">
                    <button
                      onClick={() => setOpenFaq(open ? null : i)}
                      className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left hover:bg-brand-bg/50 transition-colors"
                      aria-expanded={open}
                    >
                      <span className="type-label text-brand-primary">{item.q}</span>
                      <ChevronDown size={18} className={`shrink-0 text-brand-muted transition-transform ${open ? "rotate-180" : ""}`} />
                    </button>
                    {open && <div className="px-5 pb-4 type-body text-brand-muted-strong">{item.a}</div>}
                  </div>
                );
              })}
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}
