import React, { useEffect, useState, useRef } from "react";
import { createRoot } from "react-dom/client";
import {
  api,
  ApiError,
  type Application,
  type Consent,
  type Profile,
  type Program,
  type LearnerData,
  type Page,
  type Dashboard,
  type ProfileDocument,
} from "./api";
import "./style.css";
import {
  LearnerFields,
  learnerFieldsOf,
  emptyLearner,
  fieldLabels,
  validateLearner,
  ProfileEditor,
  SecurityPanel,
  AuthRecovery,
  DashboardPanel,
  NotificationsPanel,
  DocumentsPanel,
  ApplicationTable,
  Pager,
} from "./CabinetPanels";
import { titleKey } from "./ProfileDocuments";
import { StatementDocument, ContractEditor, ContractRegistry, ProgramDocumentSettings } from "./GeneratedDocuments";

function Brand() {
  return (
    <div className="brand">
      <img
        className="brand-logo"
        src="/brand/mospolytech-black.svg"
        alt="Московский Политех"
        width={290.9}
        height={76.6}
      />
      <div className="wordmark">Портал ДПО</div>
    </div>
  );
}

type Fields = {
  last_name: string;
  first_name: string;
  patronymic: string;
  email: string;
};
const labels: Record<string, string> = {
  last_name: "Фамилия",
  first_name: "Имя",
  patronymic: "Отчество",
  email: "Email",
  password: "Пароль",
  password_confirm: "Подтверждение пароля",
  documents: "Документы",
  consent: "Согласие",
  consent_version: "Версия согласия",
  reason: "Причина",
  file: "Файл",
  detail: "",
  non_field_errors: "",
};
const dates = (value: string) => new Date(value).toLocaleDateString("ru-RU");
const actions: Record<string, string> = {
  contract_registered: "Договор зарегистрирован",
  created: "Заявка создана",
  submitted: "Отправлена на проверку",
  accepted: "Заявка принята",
  rejected: "Заявка отклонена",
};
const fieldsOf = (p: Fields): Fields => ({
  last_name: p.last_name,
  first_name: p.first_name,
  patronymic: p.patronymic,
  email: p.email,
});

function PersonalFields({
  value,
  change,
  disabled = false,
  errors = null,
}: {
  value: Fields;
  change: (v: Fields) => void;
  disabled?: boolean;
  errors?: Record<string, unknown> | null;
}) {
  return (
    <div className="fields">
      {(Object.keys(value) as (keyof Fields)[]).map((key) => (
        <label key={key}>
          {labels[key]}
          {key === "patronymic" && (
            <span className="muted"> · необязательно</span>
          )}
          <input
            aria-invalid={!!errors?.[key]}
            aria-describedby={errors?.[key] ? `auth-${key}-error` : undefined}
            disabled={disabled}
            required={key !== "patronymic"}
            type={key === "email" ? "email" : "text"}
            maxLength={key === "email" ? 254 : 150}
            autoComplete={
              key === "email"
                ? "email"
                : key === "first_name"
                  ? "given-name"
                  : key === "last_name"
                    ? "family-name"
                    : "additional-name"
            }
            value={value[key]}
            onChange={(e) => change({ ...value, [key]: e.target.value })}
          />
          {errors?.[key] != null && (
            <small className="field-error" id={`auth-${key}-error`}>
              {String(errors[key])}
            </small>
          )}
        </label>
      ))}
    </div>
  );
}

function App() {
  const [user, setUser] = useState<Profile | null>(null);
  const [consentText, setConsentText] = useState<Consent>({
    version: "",
    text: "",
    available: false,
  });
  const [initializing, setInitializing] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Record<string, unknown> | null>(null);
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState("dashboard");
  const [register, setRegister] = useState(false);
  const [profile, setProfile] = useState<Fields>({
    last_name: "",
    first_name: "",
    patronymic: "",
    email: "",
  });
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [programs, setPrograms] = useState<Program[]>([]);
  const [profileDocuments, setProfileDocuments] = useState<ProfileDocument[]>(
    [],
  );
  const [mobileMenu, setMobileMenu] = useState(false);
  const [applications, setApplications] = useState<Application[]>([]);
  const [selected, setSelected] = useState<Application | null>(null);
  const [draft, setDraft] = useState<LearnerData>({
    ...emptyLearner,
    ...profile,
  });
  const [profileDirty, setProfileDirty] = useState(false);
  const [contractDirty, setContractDirty] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [ordering, setOrdering] = useState("-created_at");
  const [unread, setUnread] = useState(0);
  const requestPending = useRef(false);
  const [resetLink, setResetLink] = useState<{
    uid: string;
    token: string;
  } | null>(() => {
    const parts = location.hash.split("/");
    return parts[0] === "#reset" && parts[1] && parts[2]
      ? { uid: parts[1], token: parts[2] }
      : null;
  });
  const [recovery, setRecovery] = useState(location.hash.startsWith("#reset/"));
  const draftDirty =
    tab === "detail" &&
    selected?.status === "draft" &&
    JSON.stringify(draft) !== JSON.stringify(learnerFieldsOf(selected));
  const unsaved = profileDirty || draftDirty || contractDirty;
  function allowLeave() {
    return (
      !unsaved ||
      window.confirm("Есть несохранённые изменения. Уйти без сохранения?")
    );
  }
  useEffect(() => {
    if (location.hash.startsWith("#reset/"))
      history.replaceState(null, "", location.pathname);
  }, []);
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (unsaved) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [unsaved]);
  useEffect(() => {
    if (!user) return;
    const update = () => {
      void api<Dashboard>("dashboard/")
        .then((d) => setUnread(d.unread))
        .catch(() => {});
    };
    update();
    const timer = window.setInterval(update, 30000);
    return () => window.clearInterval(timer);
  }, [user]);
  const [consent, setConsent] = useState(false);
  const [reason, setReason] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");

  async function perform(fn: () => Promise<void>) {
    if (requestPending.current) return;
    requestPending.current = true;
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.details
          : { detail: "Не удалось выполнить действие. Повторите попытку." },
      );
    } finally {
      requestPending.current = false;
      setBusy(false);
    }
  }
  async function loadApplications(
    query = search,
    status = filter,
    requestedPage = 1,
    requestedOrdering = ordering,
  ) {
    const data = await api<Page<Application>>(
      `applications/?page=${requestedPage}&search=${encodeURIComponent(query)}&status=${encodeURIComponent(status)}&ordering=${requestedOrdering}`,
    );
    setApplications(data.results);
    setPage(requestedPage);
    setTotal(data.count);
  }
  async function loadCabinet(p: Profile) {
    const [loadedPrograms, loadedDocuments, loadedApplications] =
      await Promise.all([
        api<Program[]>("programs/"),
        p.role === "student"
          ? api<ProfileDocument[]>("profile/documents/")
          : Promise.resolve([] as ProfileDocument[]),
        api<Page<Application>>(
          "applications/?page=1&search=&status=&ordering=-created_at",
        ),
      ]);
    setSearch("");
    setFilter("");
    setOrdering("-created_at");
    setUnread(0);
    setUser(p);
    setProfile(fieldsOf(p));
    setTab(p.role === "operator" ? "applications" : "profile");
    setSelected(null);
    setPrograms(loadedPrograms);
    setProfileDocuments(loadedDocuments);
    setApplications(loadedApplications.results);
    setPage(1);
    setTotal(loadedApplications.count);
  }
  async function restore() {
    setInitializing(true);
    setError(null);
    try {
      const result = await api<{ user: Profile | null; consent: Consent }>(
        "session/",
      );
      setConsentText(result.consent);
      if (result.user) await loadCabinet(result.user);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.details : { detail: "Ошибка загрузки." },
      );
    } finally {
      setInitializing(false);
    }
  }
  useEffect(() => {
    void restore();
  }, []);

  function openApplication(app: Application) {
    setSelected(app);
    setDraft(learnerFieldsOf(app));
    setConsent(false);
    setReason("");
    setError(null);
    setNotice("");
    setTab("detail");
  }
  async function saveDraft() {
    if (!selected) return null;
    const validation = validateLearner(draft);
    if (Object.keys(validation).length) throw new ApiError(validation);
    const result = await api<Application>(
      `applications/${selected.id}/`,
      "PATCH",
      draft,
    );
    setSelected(result);
    return result;
  }
  async function refreshSelected(id: number) {
    const current = await api<Application>(`applications/${id}/`);
    setSelected(current);
    await loadApplications(search, filter);
  }
  const errors = error && (
    <div className="alert error" role="alert">
      <strong>Не удалось выполнить действие</strong>
      <ul>
        {Object.entries(error).map(([k, v]) => (
          <li key={k}>
            {labels[k] ? `${labels[k]}: ` : ""}
            {Array.isArray(v) ? v.join(" ") : String(v)}
          </li>
        ))}
      </ul>
    </div>
  );
  const feedback = (
    <>
      {errors}
      {notice && (
        <div className="alert success" role="status">
          {notice}
        </div>
      )}
    </>
  );

  if (initializing)
    return (
      <div className="loading" role="status">
        Загружаем Портал ДПО…
      </div>
    );
  if (!user || (recovery && resetLink))
    return (
      <div className="auth-layout">
        <aside className="auth-intro">
          <Brand />
          <div>
            <div className="eyebrow">
              Дополнительное профессиональное образование
            </div>
            <h1>
              Новый этап
              <br />
              вашего развития.
            </h1>
            <p>
              Программы обучения, подача документов и результаты проверки — в
              одном личном кабинете.
            </p>
          </div>
          <small>
            Московский Политех · Дополнительное профессиональное образование
          </small>
        </aside>
        <main className="auth-main">
          <div className="auth-box">
            {recovery ? (
              <AuthRecovery
                reset={resetLink}
                onClose={() => {
                  if (resetLink) setUser(null);
                  setRecovery(false);
                  setResetLink(null);
                  setRegister(false);
                  setError(null);
                }}
              />
            ) : (
              <>
                <div className="eyebrow">Личный кабинет</div>
                <h2>{register ? "Создать аккаунт" : "С возвращением"}</h2>
                <p className="muted">
                  {register
                    ? "Регистрация обучающегося"
                    : "Войдите по email и паролю"}
                </p>
                {feedback}
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void perform(async () => {
                      const result = await api<{ user: Profile }>(
                        `auth/${register ? "register" : "login"}/`,
                        "POST",
                        register
                          ? { ...profile, password, password_confirm: confirm }
                          : { email: profile.email, password },
                      );
                      setPassword("");
                      setConfirm("");
                      await loadCabinet(result.user);
                    });
                  }}
                >
                  {register ? (
                    <PersonalFields
                      value={profile}
                      change={setProfile}
                      errors={error}
                    />
                  ) : (
                    <label>
                      Email
                      <input
                        aria-invalid={!!error?.email}
                        type="email"
                        required
                        autoComplete="username"
                        value={profile.email}
                        onChange={(e) =>
                          setProfile({ ...profile, email: e.target.value })
                        }
                      />
                      {error?.email != null && (
                        <small className="field-error">
                          {String(error.email)}
                        </small>
                      )}
                    </label>
                  )}
                  <label>
                    Пароль
                    <input
                      aria-invalid={!!error?.password}
                      type="password"
                      required
                      autoComplete={
                        register ? "new-password" : "current-password"
                      }
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                    {error?.password != null && (
                      <small className="field-error">
                        {String(error.password)}
                      </small>
                    )}
                  </label>
                  {register && (
                    <>
                      <p className="hint">
                        Не менее 8 символов. Пароль не должен состоять только из
                        цифр, быть распространённым или похожим на ваши данные.
                      </p>
                      <label>
                        Подтверждение пароля
                        <input
                          aria-invalid={!!error?.password_confirm}
                          type="password"
                          required
                          autoComplete="new-password"
                          value={confirm}
                          onChange={(e) => setConfirm(e.target.value)}
                        />
                        {error?.password_confirm != null && (
                          <small className="field-error">
                            {String(error.password_confirm)}
                          </small>
                        )}
                      </label>
                    </>
                  )}
                  <button className="primary full" disabled={busy}>
                    {busy
                      ? "Подождите…"
                      : register
                        ? "Зарегистрироваться"
                        : "Войти"}
                  </button>
                </form>
                <button
                  className="text-button full"
                  disabled={busy}
                  onClick={() => {
                    setRegister(!register);
                    setError(null);
                    setPassword("");
                    setConfirm("");
                  }}
                >
                  {register
                    ? "Уже есть аккаунт? Войти"
                    : "Нет аккаунта? Зарегистрироваться"}
                </button>
                {!register && (
                  <button
                    className="text-button full"
                    disabled={busy}
                    onClick={() => {
                      setRecovery(true);
                      setError(null);
                      setNotice("");
                    }}
                  >
                    Забыли пароль?
                  </button>
                )}
              </>
            )}
            {error && (
              <button className="text-button" onClick={() => void restore()}>
                Повторить загрузку сессии
              </button>
            )}
          </div>
        </main>
      </div>
    );

  const operator = user.role === "operator";
  const navigation = operator
    ? [
        ["applications", "Заявки"],
        ["contracts", "Реестр договоров"],
        ["program-settings", "Реквизиты программ"],
        ["dashboard", "Обзор работы"],
        ["notifications", "Уведомления"],
        ["profile", "Мой профиль"],
      ]
    : [
        ["profile", "Мой профиль"],
        ["applications", "Мои заявки"],
        ["programs", "Образовательные программы"],
        ["notifications", "Уведомления"],
        ["documents", "Документы в заявках"],
        ["dashboard", "Обзор"],
      ];
  const navigate = (next: string) => {
    if (!allowLeave()) return;
    setProfileDirty(false);
    setTab(next);
    setSelected(null);
    setError(null);
    setNotice("");
    setMobileMenu(false);
    window.scrollTo({ top: 0 });
    if (next === "applications")
      void perform(() => loadApplications(search, filter));
  };
  return (
    <div className="shell">
      <aside className="sidebar">
        <Brand />
        <button
          className="mobile-menu-toggle secondary"
          aria-expanded={mobileMenu}
          aria-controls="cabinet-navigation"
          onClick={() => setMobileMenu(!mobileMenu)}
        >
          {mobileMenu ? "Закрыть меню ↑" : "Разделы кабинета ↓"}
        </button>
        <div className="role-label">
          {operator ? "Кабинет оператора" : "Кабинет обучающегося"}
        </div>
        <nav
          id="cabinet-navigation"
          className={mobileMenu ? "is-open" : ""}
          aria-label="Главная навигация"
        >
          {navigation.map(([id, label]) => (
            <button
              key={id}
              className={
                tab === id || (id === "applications" && tab === "detail")
                  ? "active"
                  : ""
              }
              disabled={busy}
              aria-current={
                tab === id || (id === "applications" && tab === "detail")
                  ? "page"
                  : undefined
              }
              onClick={() => navigate(id)}
            >
              {label}
              {id === "notifications" && unread > 0 && (
                <span className="unread-counter" aria-label="непрочитанные">
                  {unread}
                </span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button
            className="text-button"
            disabled={busy}
            aria-current={tab === "security" ? "page" : undefined}
            onClick={() => navigate("security")}
          >
            Безопасность
          </button>
          <strong>
            {user.first_name} {user.last_name}
          </strong>
          <small>{user.email}</small>
          <button
            className="text-button"
            disabled={busy}
            onClick={() => {
              if (!allowLeave()) return;
              setProfileDirty(false);
              void perform(async () => {
                await api("auth/logout/", "POST");
                setUser(null);
                setSelected(null);
                setApplications([]);
                setProfile({
                  last_name: "",
                  first_name: "",
                  patronymic: "",
                  email: "",
                });
                setRegister(false);
              });
            }}
          >
            Выйти из аккаунта
          </button>
        </div>
      </aside>
      <main className="workspace">
        <header>
          <span>Дополнительное профессиональное образование</span>
          <span className="account-tag">
            {operator ? "Оператор" : "Обучающийся"}
          </span>
        </header>
        <div className="content">
          {consentText.kind === "prototype" && (
            <p className="demo-banner" role="note">
              Учебный прототип · Доступны подача заявки и её рассмотрение
              оператором. Согласие используется для демонстрации проекта и не
              является утверждённым документом университета.
            </p>
          )}
          {consentText.kind === "demo_confirmation" && (
            <p className="demo-banner" role="note">
              Демонстрационный портал · Только вымышленные данные и тестовые
              файлы. Подтверждение не является официальным согласием
              университета.
            </p>
          )}
          {feedback}
          {busy && (
            <div className="busy" role="status">
              Выполняем запрос…
            </div>
          )}
          {tab === "dashboard" && (
            <DashboardPanel
              operator={operator}
              onUnread={setUnread}
              onNavigate={navigate}
              onOpen={(id) =>
                void perform(async () => {
                  if (!allowLeave()) return;
                  openApplication(
                    await api<Application>(`applications/${id}/`),
                  );
                })
              }
            />
          )}
          {tab === "notifications" && (
            <NotificationsPanel
              onUnread={setUnread}
              onOpen={(id) =>
                void perform(async () =>
                  openApplication(
                    await api<Application>(`applications/${id}/`),
                  ),
                )
              }
            />
          )}
          {tab === "documents" && !operator && (
            <DocumentsPanel
              onOpen={(id) =>
                void perform(async () =>
                  openApplication(
                    await api<Application>(`applications/${id}/`),
                  ),
                )
              }
            />
          )}
          {tab === "security" && <SecurityPanel onDirty={setProfileDirty} />}
          {tab === "programs" && !operator && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">Обучение и развитие</div>
                  <h1>Образовательные программы</h1>
                  <p className="muted">
                    Выберите программу и отправьте документы на проверку.
                  </p>
                </div>
                <div className="counter">
                  {programs.length}
                  <small>программы</small>
                </div>
              </div>
              <div className="program-grid">
                {programs.map((p, i) => (
                  <article className="program-card" key={p.id}>
                    <div className="card-top">
                      <span className="eyebrow">Программа ДПО</span>
                      <span className="program-number">0{i + 1}</span>
                    </div>
                    <h2>{p.title}</h2>
                    <p>{p.description}</p>
                    <div className="program-meta">
                      <strong>{p.hours} часов</strong>
                      <span>
                        {dates(p.starts_on)} — {dates(p.ends_on)}
                      </span>
                    </div>
                    <div className="requirements">
                      <strong>Для подачи заявки</strong>
                      <ul>
                        {p.requirements.map((r) => (
                          <li key={r.id}>
                            {r.title}
                            {r.only_if_graduated
                              ? " — если документ уже получен"
                              : r.required
                                ? " — обязательно"
                                : " — необязательно"}
                          </li>
                        ))}
                      </ul>
                    </div>
                    {!!p.profile_missing_fields?.length && (
                      <p className="hint">
                        В профиле не хватает:{" "}
                        {p.profile_missing_fields
                          .map((f) => f.label)
                          .join(", ")}
                        .
                      </p>
                    )}
                    {!p.submission_availability.available && (
                      <div className="availability-message" role="note">
                        <strong>Отправка пока недоступна</strong>
                        <p>{p.submission_availability.reason}</p>
                        <p className="hint">
                          {p.submission_availability.next_step}
                        </p>
                      </div>
                    )}
                    <button
                      className="primary"
                      disabled={busy}
                      onClick={() =>
                        void perform(async () => {
                          const app = await api<Application>(
                            "applications/",
                            "POST",
                            { program: p.id },
                          );
                          openApplication(app);
                          await loadApplications();
                        })
                      }
                    >
                      {p.submission_availability.available
                        ? "Подать заявку"
                        : "Создать черновик"}{" "}
                      <span aria-hidden="true">→</span>
                    </button>
                  </article>
                ))}
              </div>
              {!programs.length && (
                <div className="empty">
                  Программы пока не опубликованы. Уточните сроки приёма у
                  сотрудника ДПО.
                </div>
              )}
            </>
          )}
          {tab === "profile" && (
            <ProfileEditor
              user={user}
              programs={programs}
              documents={profileDocuments}
              onDocumentsChanged={setProfileDocuments}
              onNavigate={navigate}
              onApply={(programId) =>
                perform(async () => {
                  const app = await api<Application>("applications/", "POST", {
                    program: programId,
                  });
                  openApplication(app);
                  await loadApplications();
                })
              }
              onDirty={setProfileDirty}
              onSaved={async (p) => {
                setUser(p);
                setProfile(fieldsOf(p));
                setPrograms(await api<Program[]>("programs/"));
              }}
            />
          )}
          {tab === "program-settings" && operator && <ProgramDocumentSettings programs={programs} onSaved={updated => setPrograms(programs.map(p => p.id === updated.id ? updated : p))} />}
          {tab === "contracts" && operator && <ContractRegistry onOpen={id => void perform(async () => openApplication(await api<Application>(`applications/${id}/`)))} />}
          {tab === "applications" && (
            <>
              <div className="eyebrow">
                {operator ? "Приём документов" : "Личный кабинет"}
              </div>
              <div className="page-heading">
                <h1>{operator ? "Заявки" : "Мои заявки"}</h1>
                {!operator && (
                  <button
                    className="primary"
                    onClick={() => navigate("programs")}
                  >
                    Подать новую заявку →
                  </button>
                )}
              </div>
              <p className="muted">
                {operator
                  ? "Проверьте документы и примите решение. Черновики обучающихся здесь не отображаются."
                  : "Следите за статусом подачи и результатами проверки документов."}
              </p>
              <form
                className="filters"
                onSubmit={(e) => {
                  e.preventDefault();
                  void perform(() => loadApplications(search, filter));
                }}
              >
                <label>
                  Поиск
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Программа, фамилия, email или №"
                  />
                </label>
                <label>
                  Статус
                  <select
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                  >
                    <option value="">Все статусы</option>
                    {!operator && <option value="draft">Черновик</option>}
                    <option value="review">На проверке</option>
                    <option value="accepted">Принята</option>
                    <option value="rejected">Отклонена</option>
                  </select>
                </label>
                <label>
                  Сортировка
                  <select
                    value={ordering}
                    onChange={(e) => setOrdering(e.target.value)}
                  >
                    <option value="-created_at">Сначала новые</option>
                    <option value="created_at">Сначала старые</option>
                    <option value="number">По номеру</option>
                    <option value="status">По статусу</option>
                    <option value="-submitted_at">По дате отправки</option>
                  </select>
                </label>
                <button className="secondary" disabled={busy}>
                  Найти
                </button>
              </form>
              {!!applications.length && (
                <ApplicationTable
                  items={applications}
                  operator={operator}
                  busy={busy}
                  onOpen={(id) =>
                    void perform(async () =>
                      openApplication(
                        await api<Application>(`applications/${id}/`),
                      ),
                    )
                  }
                />
              )}
              <Pager
                page={page}
                total={total}
                busy={busy}
                onPage={(next) =>
                  void perform(() => loadApplications(search, filter, next))
                }
              />
              {!applications.length && (
                <div className="empty">
                  <h2>Заявок пока нет</h2>
                  <p>
                    {operator
                      ? "Нет отправленных заявок по выбранным условиям."
                      : "Выберите программу, чтобы создать первую заявку."}
                  </p>
                  {!operator && (
                    <button
                      className="primary"
                      onClick={() => navigate("programs")}
                    >
                      Выбрать программу
                    </button>
                  )}
                </div>
              )}
            </>
          )}
          {tab === "detail" && selected && (
            <>
              <button
                className="text-button back"
                disabled={busy}
                onClick={() => navigate("applications")}
              >
                ← К списку заявок
              </button>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">Заявка {selected.number}</div>
                  <h1>{selected.program.title}</h1>
                </div>
                <span className={`badge ${selected.status}`}>
                  {selected.status_label}
                </span>
              </div>
              <div className="detail-grid">
                <div>
                  <StatementDocument app={selected} unsaved={!!draftDirty} />
                  {operator && selected.status === "accepted" && <ContractEditor key={selected.id} app={selected} onDirty={setContractDirty} />}
                  {!operator && selected.contract_document && <section className="panel"><h2>Договор № {selected.contract_document.number}</h2><a href={selected.contract_document.download_url}>Скачать договор DOCX</a></section>}
                  {selected.submission_snapshot.legacy_reconstructed && (
                    <p className="info-line">
                      Для этой ранее поданной заявки доступна архивная копия.
                      Условия программы и полный текст согласия на дату подачи
                      сохранены не полностью.
                    </p>
                  )}
                  <section className="panel">
                    <h2>Данные обучающегося</h2>
                    <p className="hint">
                      {selected.status === "draft"
                        ? "Это отдельная копия данных для заявки. Изменения здесь не изменяют ваш профиль. Звёздочкой отмечены поля, обязательные при отправке."
                        : "Данные на момент отправки. Последующие изменения профиля и программы не меняют эту заявку."}
                    </p>
                    <LearnerFields
                      value={draft}
                      change={setDraft}
                      disabled={operator || selected.status !== "draft" || busy}
                      requiredFields={selected.program.required_fields}
                      errors={error}
                    />
                    {draftDirty && (
                      <p className="save-indicator" role="status">
                        Есть несохранённые изменения
                      </p>
                    )}
                    {selected.status === "draft" &&
                      !!selected.missing_fields.length && (
                        <p className="hint">
                          Для отправки заполните:{" "}
                          {selected.missing_fields
                            .map((f) => f.label)
                            .join(", ")}
                          .
                        </p>
                      )}
                    {selected.status === "draft" && !operator && (
                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={() =>
                          void perform(async () => {
                            await saveDraft();
                            await loadApplications();
                            setNotice(
                              "Черновик сохранён. Можно вернуться к нему позже.",
                            );
                          })
                        }
                      >
                        Сохранить черновик
                      </button>
                    )}
                    {selected.status === "draft" && !operator && (
                      <div className="button-row draft-actions">
                        <button
                          className="text-button"
                          disabled={busy}
                          onClick={() => {
                            if (
                              !window.confirm(
                                "Заменить данные черновика текущими данными профиля? Несохранённые изменения формы будут потеряны.",
                              )
                            )
                              return;
                            void perform(async () => {
                              const app = await api<Application>(
                                `applications/${selected.id}/refresh-profile/`,
                                "POST",
                              );
                              setSelected(app);
                              setDraft(learnerFieldsOf(app));
                              setNotice(
                                "Данные черновика обновлены из профиля.",
                              );
                            });
                          }}
                        >
                          Обновить данные из профиля
                        </button>
                        <button
                          className="danger"
                          disabled={busy}
                          onClick={() => {
                            if (
                              !window.confirm(
                                "Удалить черновик и все его вложения? Это действие нельзя отменить.",
                              )
                            )
                              return;
                            void perform(async () => {
                              await api(
                                `applications/${selected.id}/`,
                                "DELETE",
                              );
                              setSelected(null);
                              setTab("applications");
                              await loadApplications();
                              setNotice("Черновик удалён.");
                            });
                          }}
                        >
                          Удалить черновик
                        </button>
                      </div>
                    )}
                  </section>
                  <section className="panel">
                    <h2>Документы</h2>
                    <p className="muted">
                      PDF, JPEG или PNG · до 10 МБ на файл. Проверяются поля и
                      формат файлов; содержимое сканов автоматически не
                      распознаётся.
                    </p>
                    {selected.program.requirements.map((r) => {
                      const file = selected.documents.find(
                        (d) => d.requirement === r.id,
                      );
                      return (
                        <div
                          className="document"
                          key={r.id}
                          id={`requirement-${r.id}`}
                        >
                          <strong>{r.title}</strong>
                          <span className="hint">
                            {r.required &&
                            (!r.only_if_graduated ||
                              draft.education_document_received)
                              ? "Обязательный документ"
                              : r.only_if_graduated
                                ? "Необязательно, пока документ об образовании не получен"
                                : "Необязательный документ"}
                          </span>
                          {file ? (
                            <>
                              <span>
                                {file.original_name} ·{" "}
                                {file.size
                                  ? `${Math.ceil(file.size / 1024)} КБ`
                                  : "Размер не определён"}
                              </span>
                              {file.source_profile_document && (
                                <small className="readiness-ok">
                                  Прикреплена отдельная копия из профиля
                                </small>
                              )}
                              <div className="button-row">
                                <a
                                  href={file.preview_url}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  Просмотреть
                                </a>
                                <a href={file.download_url}>Скачать</a>
                                {!operator && selected.status === "draft" && (
                                  <button
                                    className="text-button"
                                    disabled={busy}
                                    onClick={() => {
                                      if (
                                        !window.confirm(
                                          "Удалить это вложение из черновика?",
                                        )
                                      )
                                        return;
                                      void perform(async () => {
                                        setSelected(
                                          await api<Application>(
                                            `documents/${file.id}/`,
                                            "DELETE",
                                          ),
                                        );
                                        setNotice("Вложение удалено.");
                                      });
                                    }}
                                  >
                                    Удалить вложение
                                  </button>
                                )}
                              </div>
                            </>
                          ) : (
                            <span className="muted">Документ не добавлен</span>
                          )}
                          {!operator && selected.status === "draft" && (
                            <label>
                              Использовать документ из профиля
                              <select
                                disabled={busy}
                                value=""
                                onChange={(e) => {
                                  if (!e.target.value) return;
                                  const source = Number(e.target.value);
                                  void perform(async () => {
                                    setSelected(
                                      await api<Application>(
                                        `applications/${selected.id}/profile-document/`,
                                        "POST",
                                        { document: source, requirement: r.id },
                                      ),
                                    );
                                    setNotice(
                                      "Документ из профиля прикреплён к заявке.",
                                    );
                                  });
                                }}
                              >
                                <option value="">
                                  {profileDocuments.some(
                                    (d) =>
                                      titleKey(d.title) === titleKey(r.title),
                                  )
                                    ? "Выберите сохранённый файл"
                                    : "В профиле пока нет подходящих файлов"}
                                </option>
                                {profileDocuments
                                  .filter(
                                    (d) =>
                                      titleKey(d.title) === titleKey(r.title),
                                  )
                                  .map((d) => (
                                    <option key={d.id} value={d.id}>
                                      {d.original_name} ·{" "}
                                      {new Date(d.uploaded_at).toLocaleString(
                                        "ru-RU",
                                      )}
                                    </option>
                                  ))}
                              </select>
                            </label>
                          )}
                          {!operator && selected.status === "draft" && (
                            <label className="upload-label">
                              {file ? "Заменить файл" : "Выбрать файл"}
                              <input
                                type="file"
                                disabled={busy}
                                accept=".pdf,.jpg,.jpeg,.png"
                                onChange={(e) => {
                                  const file = e.target.files?.[0];
                                  e.target.value = "";
                                  if (!file) return;
                                  if (file.size > 10 * 1024 * 1024) {
                                    setError({
                                      file: "Размер файла превышает 10 МБ.",
                                    });
                                    return;
                                  }
                                  void perform(async () => {
                                    const form = new FormData();
                                    form.append("file", file);
                                    form.append("requirement", String(r.id));
                                    setSelected(
                                      await api<Application>(
                                        `applications/${selected.id}/documents/`,
                                        "POST",
                                        form,
                                      ),
                                    );
                                    setNotice(
                                      "Документ загружен. Изменения полей сохраните кнопкой «Сохранить черновик» или при отправке.",
                                    );
                                  });
                                }}
                              />
                            </label>
                          )}
                          {(error?.[`document_${r.id}`] ||
                            error?.documents ||
                            error?.file) != null && (
                            <p className="field-error" role="alert">
                              {String(
                                error?.[`document_${r.id}`] ||
                                  error?.documents ||
                                  error?.file,
                              )}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </section>
                  {!operator &&
                    selected.status === "draft" &&
                    !selected.submission_availability.available && (
                      <section className="panel">
                        <h2>Отправка на проверку</h2>
                        <p>{selected.submission_availability.reason}</p>
                        <p className="hint">
                          {selected.submission_availability.next_step}
                        </p>
                      </section>
                    )}
                  {!operator &&
                    selected.status === "draft" &&
                    selected.submission_availability.available && (
                      <section className="panel">
                        <h2>Отправка на проверку</h2>
                        <p>
                          Проверьте личные данные и каждый прикреплённый
                          документ. После отправки изменить заявку нельзя.
                        </p>
                        {!!selected.missing_documents.length && (
                          <p className="hint">
                            Добавьте документы:{" "}
                            {selected.missing_documents
                              .map((d) => d.title)
                              .join(", ")}
                            .
                          </p>
                        )}
                        {consentText.kind === "demo_confirmation" && (
                          <p className="info-line">
                            Демонстрационное подтверждение · Не является
                            утверждённым согласием Московского Политеха.
                          </p>
                        )}
                        {consentText.kind === "prototype" && (
                          <h3>Согласие на обработку персональных данных</h3>
                        )}
                        <p className="consent-text">{consentText.text}</p>
                        <label className="checkbox">
                          <input
                            id="application-consent"
                            type="checkbox"
                            checked={consent}
                            disabled={busy}
                            onChange={(e) => setConsent(e.target.checked)}
                          />
                          <span>
                            {consentText.kind === "demo_confirmation"
                              ? "Подтверждаю использование только вымышленных сведений и тестовых файлов · версия"
                              : consentText.kind === "prototype"
                                ? "Я согласен на обработку персональных данных в учебном прототипе · версия"
                                : "Согласен на обработку персональных данных · версия"}{" "}
                            {consentText.version}
                          </span>
                        </label>
                        {(error?.consent || error?.consent_version) != null && (
                          <p className="field-error" role="alert">
                            {String(error?.consent || error?.consent_version)}
                          </p>
                        )}
                        <button
                          className="primary"
                          disabled={busy}
                          onClick={() =>
                            void perform(async () => {
                              if (!consent) {
                                document
                                  .getElementById("application-consent")
                                  ?.focus();
                                throw new ApiError({
                                  consent:
                                    "Отметьте согласие на обработку персональных данных перед отправкой заявки.",
                                });
                              }
                              if (
                                !window.confirm(
                                  "Отправить заявку? После отправки изменить данные и вложения нельзя.",
                                )
                              )
                                return;
                              await saveDraft();
                              await api(
                                `applications/${selected.id}/submit/`,
                                "POST",
                                {
                                  consent,
                                  consent_version: consentText.version,
                                },
                              );
                              await refreshSelected(selected.id);
                              setNotice("Заявка отправлена на проверку.");
                            })
                          }
                        >
                          Отправить на проверку →
                        </button>
                      </section>
                    )}
                  {operator && selected.status === "review" && (
                    <section className="panel">
                      <h2>Решение по заявке</h2>
                      <p className="muted">
                        Принятие завершает ручную проверку. Оно не означает
                        подписание договора или зачисление.
                      </p>
                      <label>
                        Причина решения
                        <textarea
                          value={reason}
                          maxLength={4000}
                          onChange={(e) => setReason(e.target.value)}
                          placeholder="Для отклонения причина обязательна"
                        />
                        {error?.reason != null && (
                          <small className="field-error">
                            {String(error.reason)}
                          </small>
                        )}
                      </label>
                      <div className="button-row">
                        <button
                          className="primary"
                          disabled={busy}
                          onClick={() =>
                            void perform(async () => {
                              if (
                                !window.confirm(
                                  "Принять заявку? Решение будет окончательным.",
                                )
                              )
                                return;
                              await api(
                                `applications/${selected.id}/decision/`,
                                "POST",
                                { decision: "accepted", reason },
                              );
                              await refreshSelected(selected.id);
                              setNotice("Заявка принята.");
                            })
                          }
                        >
                          Принять заявку
                        </button>
                        <button
                          className="danger"
                          disabled={busy}
                          onClick={() =>
                            void perform(async () => {
                              if (!reason.trim())
                                throw new ApiError({
                                  reason: "Укажите причину отклонения.",
                                });
                              if (
                                !window.confirm(
                                  "Отклонить заявку с указанной причиной? Решение будет окончательным.",
                                )
                              )
                                return;
                              await api(
                                `applications/${selected.id}/decision/`,
                                "POST",
                                { decision: "rejected", reason },
                              );
                              await refreshSelected(selected.id);
                              setNotice("Заявка отклонена.");
                            })
                          }
                        >
                          Отклонить
                        </button>
                      </div>
                    </section>
                  )}
                  {["accepted", "rejected"].includes(selected.status) && (
                    <section className="panel">
                      <h2>
                        Результат проверки:{" "}
                        {selected.status_label.toLowerCase()}
                      </h2>
                      {selected.decision_reason && (
                        <p className="reason">{selected.decision_reason}</p>
                      )}
                      <p className="muted">
                        {selected.status === "accepted"
                          ? "Ручная проверка завершена. Принятие не является зачислением или подписанием договора."
                          : "Заявка закрыта для редактирования и повторной отправки. Для повторной подачи создайте новую заявку через каталог программ."}
                      </p>
                    </section>
                  )}
                </div>
                <aside>
                  <section className="panel">
                    <div className="eyebrow">Программа</div>
                    <h3>{selected.program.hours} часов</h3>
                    <p>
                      {dates(selected.program.starts_on)} —{" "}
                      {dates(selected.program.ends_on)}
                    </p>
                    {selected.program.lms_url &&
                      (selected.program.lms_url.includes("example.invalid") ? (
                        <p className="hint">
                          Ссылка на СДО пока не опубликована.
                        </p>
                      ) : (
                        <a
                          href={selected.program.lms_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Перейти в СДО ↗
                        </a>
                      ))}
                  </section>
                  <section className="panel">
                    <h2>История заявки</h2>
                    <ol className="timeline">
                      {selected.events.map((event) => (
                        <li key={event.id}>
                          <strong>
                            {actions[event.action] || event.action}
                          </strong>
                          <small>
                            {new Date(event.created_at).toLocaleString("ru-RU")}{" "}
                            · {event.actor_name}
                          </small>
                          {event.reason && (
                            <p className="reason">{event.reason}</p>
                          )}
                        </li>
                      ))}
                    </ol>
                    {selected.submission_snapshot.consent?.text && (
                      <details className="consent-archive">
                        <summary>
                          {selected.consent_version === "demo-confirmation-v1"
                            ? "Принятый текст демонстрационного подтверждения"
                            : "Принятый текст согласия"}
                        </summary>
                        <p className="consent-text">
                          {selected.submission_snapshot.consent.text}
                        </p>
                      </details>
                    )}
                    {selected.consent_at && (
                      <p className="hint">
                        {selected.consent_version === "demo-confirmation-v1"
                          ? "Демонстрационное подтверждение зафиксировано"
                          : "Согласие зафиксировано"}{" "}
                        {new Date(selected.consent_at).toLocaleString("ru-RU")}{" "}
                        · {selected.consent_version}
                      </p>
                    )}
                  </section>
                </aside>
              </div>
            </>
          )}
        </div>
        <footer>
          Московский Политех · Портал дополнительного профессионального
          образования
        </footer>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
