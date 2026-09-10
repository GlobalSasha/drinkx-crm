"use client";

// /guide — краткое руководство, подстроенное под роль открывшего.
// Менеджер видит свой минимум, руководитель — раздачу базы, задачи команде
// и панель «Сегодня». Детали не выброшены, а убраны в раскрывашки «Подробнее»:
// на виду остаётся то, что нужно каждый день.
//
// Содержание выверено по коду (сентябрь 2026): 6 вкладок карточки лида,
// задачи можно ставить без клиента, руководитель раздаёт базу и ставит
// задачи команде, «Сегодня» у руководителя — панель работы менеджеров.
//
// Якоря #quote, #incoming, #duplicates, #forecast, #team приходят из
// lib/releases.ts — они должны существовать; если якорь принадлежит другой
// роли, страница сама переключает вкладку (см. useEffect ниже).

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  CalendarDays,
  Kanban,
  Target,
  CheckSquare,
  Users,
  Settings,
  HelpCircle,
  Sparkles,
  ChevronDown,
  TrendingUp,
  Megaphone,
  ReceiptText,
  Inbox,
  BarChart3,
  ArrowRight,
  Info,
  AlertTriangle,
  Lightbulb,
  UserCog,
  Compass,
  type LucideIcon,
} from "lucide-react";

import { pageContainerVariants } from "@/components/ui/PageContainer";
import { useMe } from "@/lib/hooks/use-me";
import { RELEASES } from "@/lib/releases";
import { ReleaseCard } from "@/components/guide/ReleaseCard";

type View = "manager" | "head";

// ─── Оглавление ──────────────────────────────────────────────────

const TOC: Record<View, { id: string; label: string; icon: LucideIcon }[]> = {
  manager: [
    { id: "whatsnew", label: "Что нового", icon: Megaphone },
    { id: "start", label: "С чего начать", icon: Compass },
    { id: "card", label: "Карточка лида", icon: Target },
    { id: "stages", label: "Этапы и гейты", icon: Kanban },
    { id: "tasks", label: "Задачи и файлы", icon: CheckSquare },
    { id: "quote", label: "КП", icon: ReceiptText },
    { id: "incoming", label: "Где брать клиентов", icon: Inbox },
    { id: "forecast", label: "Прогноз", icon: TrendingUp },
    { id: "faq", label: "Частые вопросы", icon: HelpCircle },
  ],
  head: [
    { id: "whatsnew", label: "Что нового", icon: Megaphone },
    { id: "start", label: "С чего начать", icon: Compass },
    { id: "today", label: "Панель «Сегодня»", icon: BarChart3 },
    { id: "pool", label: "Раздать базу", icon: Target },
    { id: "tasks", label: "Задачи команде", icon: CheckSquare },
    { id: "team", label: "Команда", icon: Users },
    { id: "forecast", label: "Прогноз", icon: TrendingUp },
    { id: "setup", label: "Настройка системы", icon: Settings },
    { id: "faq", label: "Частые вопросы", icon: HelpCircle },
  ],
};

// Якоря, которые есть только в одной из вкладок. Ссылка из «Что нового»
// на чужой раздел должна переключать вкладку, а не проваливаться в пустоту.
const MANAGER_ONLY = ["card", "stages", "quote", "incoming", "duplicates"];
const HEAD_ONLY = ["today", "pool", "team", "setup"];

// Этапы дефолтной воронки (apps/api/app/pipelines/models.py). Цвета
// приходят из настроек воронки, поэтому здесь — только названия.
const STAGES = [
  "Новый контакт",
  "Квалификация",
  "Discovery",
  "Solution Fit",
  "Business Case / КП",
  "Multi-stakeholder",
  "Договор / пилот",
  "Производство",
  "Пилот",
  "Scale / серия",
  "Закрыто (won)",
  "Закрыто (lost)",
];

const GLOSSARY: [string, string][] = [
  ["Лид", "Потенциальный клиент: компания, контакты и сделка. Главный объект работы."],
  ["Воронка", "12 этапов сделки — от «Новый контакт» до «Закрыто»."],
  ["Гейт", "Условие перехода на следующий этап. Не выполнено — система не пустит."],
  ["Fit-score", "Оценка AI (0–10): насколько лид похож на идеального клиента."],
  ["Rotting", "«Подвисший» лид — давно без движения. Виден в виджете «Устаревает»."],
  ["База лидов", "Общий банк неназначенных лидов — оттуда берут новых клиентов."],
  ["КП", "Коммерческое предложение: позиции, скидки, НДС и итог. Собирается в карточке лида."],
  ["Архив", "Куда уезжают «удалённые» задачи — вместе с файлами. Восстанавливаются в один клик."],
];

const FAQ: Record<View, [string, string][]> = {
  manager: [
    [
      "Не могу перевести лид на следующий этап",
      "Не выполнено условие этапа (гейт). Частый случай: начиная с «Multi-stakeholder» нужен контакт с ролью «Экономический покупатель». Карточка лида → вкладка «Контакты» → добавьте такой контакт. Если гейт мягкий, система попросит указать причину пропуска.",
    ],
    [
      "Как поставить задачу?",
      "Двумя способами. В карточке лида — вкладка «Задачи» или прямо в ленте «Активность» (переключатель «Задача» в поле ввода). Либо на странице «Задачи» кнопкой «Новая задача» — там клиента можно и не указывать.",
    ],
    [
      "Что значит «N дней на этапе»? Я только что взял лида",
      "Это сколько дней лид стоит на текущем этапе — независимо от того, кто им занимается. Он мог неделю висеть в базе без работы, счётчик всё это время шёл. Сколько с ним работаете лично вы — видно по дате «В работе с …».",
    ],
    [
      "Взял не тот лид",
      "Кнопка «Вернуть в базу» в шапке карточки — лид снова станет доступен всей команде.",
    ],
    [
      "Отправил задачу в архив — как вернуть?",
      "Задачи не удаляются насовсем. Карточка лида → вкладка «Архив» → «Восстановить»: задача вернётся со всеми файлами и историей.",
    ],
    [
      "Не вижу разделы «Формы», «Автоматизации», «Журнал»",
      "Они только у руководителя и администратора — для менеджера это нормально. Пункт «Команда» у менеджера ведёт в настройки.",
    ],
    [
      "Письмо от клиента не попало в карточку",
      "Значит, адрес или номер CRM не знает. Раздел «Мессенджеры» → разберите несопоставленные и привяжите к нужному лиду вручную.",
    ],
  ],
  head: [
    [
      "Как выдать менеджеру лидов?",
      "«База лидов» → отметьте карточки галочками и нажмите «Выдать» в нижней панели. Либо настройте фильтр (город, сегмент, Fit) и нажмите «Выдать по фильтру» — там задаётся, сколько первых карточек списка отдать.",
    ],
    [
      "Что значит «активное время» и «был активен»?",
      "Это разные вещи. «Активное время» — минуты реальной работы в CRM: мышь и клавиатура, простой не считается. «Был активен» — когда человек последний раз что-либо делал в системе. Звонки и встречи вне CRM в активное время не попадают — это мера работы в системе, а не рабочего дня.",
    ],
    [
      "Как поставить задачу менеджеру?",
      "«Задачи» → «Новая задача» → поле «Исполнитель». Клиента указывать необязательно. Готовую задачу можно переназначить: откройте её карандашом и смените исполнителя.",
    ],
    [
      "Как добавить нового сотрудника?",
      "Настройки → «Команда» → «Пригласить». Вход только по приглашению: человек, которого не пригласили, в рабочее пространство не попадёт, даже если у него есть Google-аккаунт.",
    ],
    [
      "Почему в «Прогнозе» нет сценариев?",
      "Оптимистичный и консервативный сценарии считаются от квот. Пока квоты не заполнены, блок пустой — это не ошибка.",
    ],
    [
      "Где видно, на каком этапе застревают сделки?",
      "«Прогноз» → таблица «Где застревают сделки»: по каждому этапу медианное время и сколько сделок стоят дольше нормы. Рядом — «Каналы привлечения» по UTM-меткам.",
    ],
    [
      "Менеджер говорит, что не видит раздел",
      "«Формы», «Автоматизации» и «Журнал» доступны только руководителю и админу. У менеджера пункт «Команда» ведёт в настройки — так и задумано.",
    ],
  ],
};

// ─── Блоки ───────────────────────────────────────────────────────

function Section({ id, icon: Icon, kicker, title, children }: {
  id: string; icon: LucideIcon; kicker: string; title: string; children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-[128px] mb-12">
      <div className="mb-5">
        <div className="flex items-center gap-2 mb-2">
          <Icon size={16} className="text-brand-accent" />
          <span className="type-caption text-brand-accent-text">{kicker}</span>
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
    <div className={`bg-white border border-brand-border rounded-card p-6 ${className}`}>
      {title && (
        <div className="flex items-center gap-2.5 mb-3">
          {Icon && (
            <span className="w-8 h-8 rounded-full bg-brand-soft flex items-center justify-center shrink-0">
              <Icon size={16} className="text-brand-accent-text" />
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
  info: { box: "bg-info/5 border-info/25", icon: Info, ic: "text-info" },
  warn: { box: "bg-warning/5 border-warning/25", icon: AlertTriangle, ic: "text-warning" },
  tip: { box: "bg-brand-soft/50 border-brand-accent/20", icon: Lightbulb, ic: "text-brand-accent" },
} as const;

function Alert({ kind, children }: { kind: keyof typeof ALERT_STYLES; children: React.ReactNode }) {
  const s = ALERT_STYLES[kind];
  const Icon = s.icon;
  return (
    <div className={`flex gap-3 items-start border rounded-card px-4 py-3.5 my-4 ${s.box}`}>
      <Icon size={18} className={`shrink-0 mt-0.5 ${s.ic}`} />
      <div className="type-body text-brand-muted-strong">{children}</div>
    </div>
  );
}

/** Раскрывашка «Подробнее» — детали, которые нужны не каждый день. */
function Details({ id, summary, children }: {
  id?: string; summary: string; children: React.ReactNode;
}) {
  return (
    <details
      id={id}
      className="group mt-3 bg-white border border-brand-border rounded-card overflow-hidden scroll-mt-[128px]"
    >
      <summary className="flex items-center justify-between gap-3 px-6 py-4 cursor-pointer list-none [&::-webkit-details-marker]:hidden type-label text-brand-primary hover:bg-brand-bg/60 transition-colors">
        {summary}
        <ChevronDown
          size={17}
          className="shrink-0 text-brand-muted transition-transform duration-150 motion-reduce:transition-none group-open:rotate-180"
        />
      </summary>
      <div className="px-6 pb-6">{children}</div>
    </details>
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

function GlossaryDetails() {
  return (
    <Details summary="Словарь: восемь слов, которые встретятся везде">
      <KV items={GLOSSARY} />
    </Details>
  );
}

// ─── Общий раздел «Прогноз» ──────────────────────────────────────

function ForecastSection() {
  return (
    <Section id="forecast" icon={TrendingUp} kicker="Деньги" title="Прогноз">
      <p className="type-body text-brand-muted-strong mb-3">
        Раздел <strong>«Прогноз»</strong> — четыре числа сверху: сколько денег в воронке,
        взвешенный прогноз (сумма с поправкой на вероятность этапа), сколько под угрозой
        и сколько закрыто за 90 дней.
      </p>
      <Details summary="Подробнее: что показывают числа и таблицы">
        <KV items={[
          ["Воронка", "Сумма всех активных сделок — все этапы, кроме закрытых."],
          ["Взвешенный прогноз", "Каждая сделка умножена на вероятность своего этапа: 5% на «Новом контакте», 75% на «Договоре». Реалистичная оценка."],
          ["Под угрозой", "Сделки, простоявшие на этапе дольше нормы. Их двигают или закрывают."],
          ["Закрыто за 90 дней", "Выигранные сделки за три месяца — мера темпа."],
          ["Воронка по сумме", "Столбики: на каком этапе сколько денег. Не число сделок, а рубли."],
          ["Каналы привлечения", "Сколько сделок и выручки принёс каждый UTM-источник. Лиды без меток — «Прямые»."],
          ["Где застревают сделки", "Медианное время на этапе и сколько сделок стоят дольше нормы."],
          ["Топ-10 «под угрозой»", "Самые дорогие из подвисших. Клик открывает карточку."],
        ]} />
      </Details>
    </Section>
  );
}

// ─── Версия для менеджера ────────────────────────────────────────

function ManagerGuide() {
  return (
    <>
      <Section id="start" icon={Compass} kicker="Утро" title="С чего начать">
        <Card title="Четыре шага, с которых начинается день" icon={CalendarDays}>
          <Steps items={[
            ["Открыть «Сегодня»", "Список задач по срокам, «Устаревает», стадии воронки. Виджеты перетаскиваются — порядок запомнится."],
            ["Закрыть, что горит", "Отметьте выполненное галочкой прямо в виджете, не заходя в карточки."],
            ["Заглянуть в «Устаревает»", "Клиенты без движения. Один звонок сегодня дешевле, чем потерянная сделка через месяц."],
            ["Добрать клиентов", "«База лидов» → «Взять в работу». Взяли — ведите; не подходит — верните в базу."],
          ]} />
        </Card>
        <GlossaryDetails />
        <Details summary="Что где лежит в меню">
          <KV items={[
            ["Поиск (⌘K)", "Компании, лиды, контакты. С трёх символов ищет с опечатками: «Мкдоналдс» найдёт «Макдоналдс»."],
            ["Сегодня", "Рабочий стол дня."],
            ["Задачи", "Все ваши задачи в одном списке, с фильтрами по сроку и статусу."],
            ["Прогноз", "Деньги в воронке и что подвисло."],
            ["Воронка", "Kanban-доска: карточки перетаскиваются между этапами. На телефоне — список."],
            ["Входящие", "Заявки с форм на сайте."],
            ["База лидов", "Общий банк неназначенных клиентов."],
            ["Мессенджеры", "Почта, Telegram, MAX и звонки. Здесь же разбираются неопознанные обращения."],
            ["База знаний", "Материалы о продукте и работе с возражениями."],
            ["Настройки", "Имя, фото, часовой пояс, специализация."],
          ]} />
        </Details>
      </Section>

      <Section id="card" icon={Target} kicker="Главный экран" title="Карточка лида">
        <p className="type-body text-brand-muted-strong mb-3">
          Всё о клиенте на одном экране. Слева — то, что нужно всегда: сумма и приоритет,
          следующий шаг, редактируемые поля сделки, основной контакт. Справа — шесть вкладок.
        </p>
        <Card>
          <KV items={[
            ["Активность", "Единая лента: комментарии, письма, звонки, файлы, смены этапа. Здесь же ставится задача или записывается звонок — переключателем в поле ввода."],
            ["Задачи", "Что нужно сделать по этому клиенту: текст, точный срок, файлы."],
            ["Контакты", "Люди со стороны клиента и их роли."],
            ["КП", "Коммерческие предложения по этому клиенту."],
            ["Заметки", "Свободные наблюдения — без срока и галочки."],
            ["Архив", "Задачи, отправленные в архив. Восстанавливаются целиком."],
          ]} />
        </Card>
        <Alert kind="info">
          Поля сделки правятся на месте: клик по строке, Enter — сохранить, Esc — отменить.
          Отдельной кнопки «редактировать карточку» нет.
        </Alert>
        <Details summary="Подробнее: действия в карточке">
          <Steps items={[
            ["Перевести на другой этап", "Клик по этапу в полосе сверху. Система проверит гейты и запишет переход."],
            ["Добавить контакт", "Вкладка «Контакты». Роль «Экономический покупатель» обязательна для поздних этапов."],
            ["Прикрепить файл", "Раскройте задачу — перетащите файл. Или в ленте «Активность» переключатель «Файл». До 25 МБ."],
            ["Собрать КП", "Вкладка «КП» — см. раздел «КП» ниже."],
            ["Вернуть, передать, закрыть", "Кнопки в шапке. «Удалить» спрятан в меню «⋯», чтобы не нажать случайно."],
          ]} />
        </Details>
        <Details id="duplicates" summary="Подробнее: у клиента завелось два лида">
          <p className="type-body text-brand-muted-strong mb-3">
            Меню <strong>«⋯» → «Найти дубли»</strong>. CRM покажет похожих по домену почты,
            телефону или названию компании. Отметьте настоящие дубликаты галочками и нажмите
            «Объединить»: текущий лид станет основным, история и контакты остальных переедут
            к нему, а сами они уйдут в архив. Автоматически ничего не склеивается — только по
            вашему выбору.
          </p>
        </Details>
      </Section>

      <Section id="stages" icon={Kanban} kicker="Воронка" title="Этапы и гейты">
        <p className="type-body text-brand-muted-strong mb-3">
          Сделка идёт по этапам слева направо. На некоторые этапы система не пустит,
          пока не собрана ключевая информация — это гейт.
        </p>
        <Alert kind="warn">
          Самый частый гейт: начиная с этапа <strong>«Multi-stakeholder»</strong> нужен контакт
          с ролью «Экономический покупатель» — тот, кто решает про деньги. Без него дальше не пройти.
        </Alert>
        <Details summary="Подробнее: все 12 этапов и мягкие гейты">
          <div className="flex flex-wrap gap-2 mb-4">
            {STAGES.map((s) => (
              <span
                key={s}
                className="inline-flex items-center bg-brand-panel border border-brand-border rounded-full px-3 py-1.5 type-label text-brand-muted-strong"
              >
                {s}
              </span>
            ))}
          </div>
          <KV items={[
            ["Мягкий гейт", "Некоторые условия можно пропустить, указав причину — она сохранится в истории."],
            ["Видимость", "Менеджер видит своих лидов, руководитель — всю команду."],
            ["Свой набор этапов", "Этапы и их критерии настраивает руководитель — у вас они могут отличаться."],
          ]} />
        </Details>
      </Section>

      <Section id="tasks" icon={CheckSquare} kicker="Планирование" title="Задачи и файлы">
        <Alert kind="info">
          Задачи ставите только вы, вручную. Никакого AI: что вписали и на какой срок — то и увидите.
        </Alert>
        <Card>
          <KV items={[
            ["Где создать", "В карточке лида (вкладка «Задачи» или лента «Активность») либо на странице «Задачи» кнопкой «Новая задача» — там клиент необязателен."],
            ["Где смотреть", "Виджет на «Сегодня», страница «Задачи», вкладка в карточке клиента."],
            ["Файлы", "Раскройте задачу и перетащите файл: PDF, картинка, Word, Excel, аудио — до 25 МБ."],
            ["Вместо удаления — архив", "Кнопка «В архив» уносит задачу вместе с файлами. Возврат — во вкладке «Архив»."],
          ]} />
        </Card>
        <Details summary="Подробнее: поиск по файлам и безопасность">
          <KV items={[
            ["Поиск внутри файлов", "Текст из PDF и расшифровка аудио индексируются: поиск по задачам находит файл по словам внутри него."],
            ["Скачивание", "Ссылка на файл одноразовая и живёт 5 минут — так файл не утечёт по пересланной ссылке."],
            ["Чего не принимает", "Исполняемые файлы (.exe и подобные) загрузить нельзя."],
          ]} />
        </Details>
      </Section>

      <Section id="quote" icon={ReceiptText} kicker="Продажи" title="Коммерческие предложения">
        <p className="type-body text-brand-muted-strong mb-3">
          КП собирается в карточке лида, вкладка <strong>«КП»</strong>. По одному клиенту можно
          вести несколько предложений, печатать их в PDF и переносить итог в сумму сделки.
        </p>
        <Alert kind="warn">
          CRM не отправляет КП клиенту сама — это намеренно. Вы сохраняете PDF и отправляете
          привычным способом.
        </Alert>
        <Details summary="Подробнее: как собрать предложение">
          <Steps items={[
            ["Новый КП", "Вкладка «КП» → «Новый КП»."],
            ["Позиции", "«+ из каталога» подставит название и цену, «+ позиция» — свободная строка. Каталог заполняет руководитель в настройках."],
            ["Скидки и НДС", "Скидка по строке и на всё предложение, ставка НДС. Итоги считаются сами."],
            ["Статус", "Черновик → «Отправлено» → «Принято» или «Отклонено». Черновик правится, отправленный фиксируется."],
            ["Печать в PDF", "Кнопка «Печать / PDF» откроет чистый лист, дальше ⌘/Ctrl+P → «Сохранить как PDF»."],
            ["Итог в сумму сделки", "Одной кнопкой переносится в поле «Сумма» сделки."],
          ]} />
        </Details>
      </Section>

      <Section id="incoming" icon={Inbox} kicker="Новые клиенты" title="Где брать клиентов">
        <div className="grid sm:grid-cols-2 gap-3">
          <Card title="База лидов" icon={Target}>
            <p className="type-body text-brand-muted-strong">
              Общий банк неназначенных компаний. Отфильтруйте по городу, сегменту и Fit-score,
              нажмите <strong>«Взять в работу»</strong> — лид появится в вашей воронке.
              Не подошёл — «Вернуть в базу».
            </p>
          </Card>
          <Card title="Входящие" icon={Inbox}>
            <p className="type-body text-brand-muted-strong">
              Заявки с форм на сайте: имя, телефон и почта (копируются в клик), вопрос клиента,
              статус. Клик по заявке открывает карточку лида — дальше работа как обычно.
            </p>
          </Card>
        </div>
        <Alert kind="tip">
          Заявка с сайта уже содержит контакт — не заводите второй лид руками. Если так вышло,
          объедините дубли из карточки.
        </Alert>
      </Section>

      <ForecastSection />
    </>
  );
}

// ─── Версия для руководителя ─────────────────────────────────────

function HeadGuide({ onSwitchToManager }: { onSwitchToManager: () => void }) {
  return (
    <>
      <Section id="start" icon={Compass} kicker="Утро" title="С чего начать">
        <Card title="Четыре шага руководителя" icon={CalendarDays}>
          <Steps items={[
            ["Открыть «Сегодня»", "Панель работы менеджеров: сколько человек работал и что с его лидами. Сверху — предупреждения: кто пропал, у кого сделки застряли."],
            ["Раздать базу", "«База лидов» → выделить карточки → «Выдать». Никто не сидит без клиентов."],
            ["Поставить задачи", "«Задачи» → «Новая задача» → исполнитель. Клиент необязателен."],
            ["Проверить деньги", "«Прогноз»: что в воронке, что под угрозой, где застревают сделки."],
          ]} />
        </Card>
        <GlossaryDetails />
      </Section>

      <Section id="today" icon={BarChart3} kicker="Ежедневно" title="Панель «Сегодня»">
        <p className="type-body text-brand-muted-strong mb-3">
          Ваш «Сегодня» отличается от менеджерского: это панель работы команды по принципу
          <strong> труд ↔ результат</strong>. Один переключатель периода сверху —
          Сегодня / Неделя / Месяц — управляет всеми числами сразу.
        </p>
        <div className="grid sm:grid-cols-2 gap-3">
          <Card title="Труд" icon={CheckSquare}>
            <p className="type-body text-brand-muted-strong">
              Активное время в CRM, новых лидов добавил, действий всего, КП отправлено.
              Полоски рядом — активность за последние 14 дней.
            </p>
          </Card>
          <Card title="Результат по его лидам" icon={TrendingUp}>
            <p className="type-body text-brand-muted-strong">
              В работе сейчас, продвинул по воронке, застряло 7+ дней, задач закрыто
              и просрочено.
            </p>
          </Card>
        </div>
        <Alert kind="warn">
          <strong>Активное время — это работа в CRM, а не рабочий день.</strong> Считаются минуты,
          когда человек действительно что-то делал в системе; звонки и встречи вне CRM сюда не
          попадают. Отметка «был активен» — про последнее действие в системе, это другое число.
        </Alert>
        <Details summary="Подробнее: как читать панель">
          <KV items={[
            ["Один менеджер", "Разворачивается в большую карточку со всеми числами и полосками по дням."],
            ["Несколько", "Таблица со строками; колонки сортируются кликом по заголовку."],
            ["Предупреждения сверху", "Кто давно не заходил и у кого лиды стоят дольше недели."],
            ["Клик по строке", "Открывает портфель менеджера — его сделки по сегментам и этапам."],
            ["«Поток заявок»", "Свёрнутая секция внизу: сколько заявок пришло за неделю и как это соотносится с прошлой."],
          ]} />
        </Details>
      </Section>

      <Section id="pool" icon={Target} kicker="Распределение" title="Раздать базу">
        <p className="type-body text-brand-muted-strong mb-3">
          В разделе <strong>«База лидов»</strong> у вас, в отличие от менеджера, есть галочки
          у строк и кнопка выдачи.
        </p>
        <Card title="Два способа">
          <Steps items={[
            ["Точечно", "Отметьте нужные строки галочками → в нижней панели «Выдать» → выберите менеджера."],
            ["Пачкой по фильтру", "Настройте фильтры (город, сегмент, приоритет, Fit) → «Выдать по фильтру» → укажите, сколько первых карточек списка отдать, и кому."],
          ]} />
        </Card>
        <Alert kind="tip">
          Выдача — не приказ, а закрепление: лид попадает в воронку менеджера, и он видит его
          как своего. Если не пошло, менеджер вернёт лид в базу сам.
        </Alert>
      </Section>

      <Section id="tasks" icon={CheckSquare} kicker="Команда" title="Задачи команде">
        <p className="type-body text-brand-muted-strong mb-3">
          На странице <strong>«Задачи»</strong> у вас три вкладки: <strong>Мои</strong>,
          <strong> Поставлено мной</strong> и <strong>Команда</strong>. Последняя — все задачи
          сотрудников, с фильтром по исполнителю.
        </p>
        <Card>
          <KV items={[
            ["Поставить задачу", "«Новая задача»: текст, срок, исполнитель. По умолчанию исполнитель — вы, поменяйте на сотрудника."],
            ["Без клиента", "Лид в задаче необязателен — можно поставить «подготовить отчёт» или «обзвонить список»."],
            ["Переназначить", "Карандаш в строке задачи → смените исполнителя."],
            ["Проконтролировать", "Вкладка «Команда» + фильтр «Просрочено» показывает всё, что горит у сотрудников."],
          ]} />
        </Card>
      </Section>

      <Section id="team" icon={Users} kicker="Разбор" title="Команда">
        <p className="type-body text-brand-muted-strong mb-3">
          Раздел <strong>«Команда»</strong> — для разбора один на один. Переключатель вида
          в правом верхнем углу и период (Сегодня / Неделя / Месяц).
        </p>
        <div className="grid sm:grid-cols-2 gap-3">
          <Card title="Manager's Dashboard" icon={BarChart3}>
            <p className="type-body text-brand-muted-strong">
              Загрузка команды: сколько у каждого активных лидов и как они разложены по этапам.
              Видно, кто перегружен, а у кого пусто.
            </p>
          </Card>
          <Card title="Активность" icon={TrendingUp}>
            <p className="type-body text-brand-muted-strong">
              Карточки по каждому за период: КП, взято из базы, продвинуто лидов, выполнено задач,
              когда был активен.
            </p>
          </Card>
        </div>
        <Alert kind="info">
          Клик по менеджеру открывает <strong>портфель сделок</strong>: суммы и количество
          по сегментам (Ритейл, HoReCa, QSR, АЗС) и по этапам. Удобно держать открытым на созвоне.
        </Alert>
      </Section>

      <ForecastSection />

      <Section id="setup" icon={Settings} kicker="Администрирование" title="Настройка системы">
        <Card>
          <KV items={[
            ["Формы", "Формы на сайт, их поля и автоответ клиенту — свой под каждую форму."],
            ["Автоматизации", "Правила: что происходит при смене этапа, при новой заявке, при молчании клиента."],
            ["Настройки → Команда", "Приглашения и роли. Вход только по приглашению."],
            ["Настройки → Каталог КП", "Товары и цены, которые менеджеры подставляют в предложения."],
            ["Настройки → Воронки", "Этапы, их вероятности и нормативные сроки — от них считаются прогноз и «под угрозой»."],
            ["Журнал", "Только у администратора: кто что менял в системе."],
          ]} />
        </Card>
        <Details summary="Подробнее: приглашения и роли">
          <KV items={[
            ["Пригласить", "Настройки → «Команда» → «Пригласить»: почта и роль. Человек получит ссылку и войдёт через Google или письмо."],
            ["Три роли", "Администратор — всё, включая журнал. Руководитель — команда, раздача, формы, автоматизации. Менеджер — свои лиды."],
            ["Без приглашения не войти", "Посторонний с рабочей почтой в пространство не попадёт."],
          ]} />
        </Details>
      </Section>

      <Section id="manager-view" icon={UserCog} kicker="Обучение" title="Что видит менеджер">
        <Card>
          <p className="type-body text-brand-muted-strong mb-4">
            Инструкция менеджера — отдельная вкладка этой же страницы. Откройте её, когда
            объясняете новичку, как работать, или разбираетесь, почему он чего-то не находит.
          </p>
          <button
            type="button"
            onClick={onSwitchToManager}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-brand-accent text-white type-button hover:opacity-90 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2"
          >
            Открыть версию менеджера
            <ArrowRight size={15} />
          </button>
        </Card>
      </Section>
    </>
  );
}

// ─── Страница ────────────────────────────────────────────────────

export default function GuidePage() {
  const { data: me } = useMe();
  const isBoss = me?.role === "head" || me?.role === "admin";

  const [override, setOverride] = useState<View | null>(null);
  const view: View = override ?? (isBoss ? "head" : "manager");

  const [openFaq, setOpenFaq] = useState<number | null>(0);

  // Ссылка из «Что нового» может вести в раздел другой роли — переключаем
  // вкладку, иначе якорь ведёт в пустоту.
  useEffect(() => {
    const hash = window.location.hash.slice(1);
    if (!hash) return;
    if (MANAGER_ONLY.includes(hash)) setOverride("manager");
    else if (HEAD_ONLY.includes(hash) && isBoss) setOverride("head");
  }, [isBoss]);

  function switchView(next: View) {
    setOverride(next);
    setOpenFaq(0);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const toc = TOC[view];
  const faq = FAQ[view];

  return (
    <div className={pageContainerVariants({ surface: "reading" })}>
      {/* Hero */}
      <div className="bg-brand-dark text-white rounded-card p-8 sm:p-10 mb-6 relative overflow-hidden">
        <div className="absolute -top-16 -right-16 w-64 h-64 rounded-full bg-brand-accent/20 blur-3xl pointer-events-none" />
        <div className="relative">
          <div className="inline-flex items-center gap-1.5 bg-white/10 text-white/90 type-caption px-3 py-1 rounded-full mb-4">
            <Sparkles size={13} /> Руководство
          </div>
          <h1 className="type-page-title mb-3">
            {view === "head" ? "Как вести команду в DrinkX CRM" : "Как работать в DrinkX CRM"}
          </h1>
          <p className="type-body text-white/70 max-w-xl">
            {view === "head"
              ? "Раздать базу, поставить задачи, увидеть, кто сколько работал и что с деньгами. Подробности — в раскрывашках, чтобы не мешали каждый день."
              : "Главное — на виду, детали — под кнопкой «Подробнее». Хватит десяти минут, чтобы начать работать."}
          </p>
        </div>
      </div>

      {/* Переключатель роли — только у руководителя и админа */}
      {isBoss && (
        <div className="flex items-center gap-3 mb-8 flex-wrap">
          <div className="inline-flex items-center gap-1 bg-brand-panel rounded-full p-1">
            {(["head", "manager"] as View[]).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => switchView(v)}
                aria-pressed={view === v}
                className={`px-4 py-1.5 rounded-full type-button transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent focus-visible:ring-offset-2 ${
                  view === v
                    ? "bg-white text-brand-primary"
                    : "text-brand-muted hover:text-brand-primary"
                }`}
              >
                {v === "head" ? "Руководитель" : "Менеджер"}
              </button>
            ))}
          </div>
          <span className="type-hint text-brand-muted">
            {view === "head"
              ? "Ваша инструкция"
              : "Смотрите то же, что видит менеджер"}
          </span>
        </div>
      )}

      <div className="grid lg:grid-cols-[220px_1fr] gap-8">
        {/* Оглавление */}
        <nav className="hidden lg:block">
          <div className="sticky top-[128px] space-y-0.5">
            {toc.map(({ id, label, icon: Icon }) => (
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
          <Section id="whatsnew" icon={Megaphone} kicker="Обновления" title="Что нового">
            <ReleaseCard release={RELEASES[0]} featured />
            <div className="mt-4">
              <Link
                href="/guide/changelog"
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-brand-panel border border-brand-border type-label text-brand-primary hover:bg-brand-border transition-colors"
              >
                История версий
                <ArrowRight size={15} />
              </Link>
            </div>
          </Section>

          {view === "head" ? (
            <HeadGuide onSwitchToManager={() => switchView("manager")} />
          ) : (
            <ManagerGuide />
          )}

          <Section id="faq" icon={HelpCircle} kicker="Справка" title="Частые вопросы">
            <div className="space-y-2.5">
              {faq.map(([q, a], i) => {
                const open = openFaq === i;
                return (
                  <div key={q} className="bg-white border border-brand-border rounded-card overflow-hidden">
                    <button
                      type="button"
                      onClick={() => setOpenFaq(open ? null : i)}
                      className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left hover:bg-brand-bg/60 transition-colors"
                      aria-expanded={open}
                    >
                      <span className="type-label text-brand-primary">{q}</span>
                      <ChevronDown
                        size={18}
                        className={`shrink-0 text-brand-muted transition-transform duration-150 motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
                      />
                    </button>
                    {open && <div className="px-5 pb-4 type-body text-brand-muted-strong">{a}</div>}
                  </div>
                );
              })}
            </div>
            <Alert kind="tip">
              Не нашли ответ — напишите в <strong>«Мессенджеры»</strong> команде поддержки или
              спросите руководителя. Раздел обновляется вместе с CRM: что изменилось — всегда
              в «Что нового» сверху.
            </Alert>
          </Section>
        </div>
      </div>
    </div>
  );
}
