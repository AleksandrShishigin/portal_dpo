import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  type Profile,
  type LearnerData,
  type Program,
  type Page,
  type Application,
  type Dashboard,
  type Notification,
  type ProfileDocument,
} from "./api";
import { ProfileDocuments, documentAnchor, titleKey } from "./ProfileDocuments";

export const fieldLabels: Record<keyof LearnerData, string> = {
  passport_series: "Серия паспорта",
  passport_number: "Номер паспорта",
  passport_issued_by: "Кем выдан паспорт",
  passport_issued_on: "Дата выдачи паспорта",
  passport_department_code: "Код подразделения паспорта",
  registration_address: "Адрес регистрации",
  residential_address: "Адрес проживания",
  snils: "СНИЛС",
  inn: "ИНН",
  referral_source: "Кто рекомендовал обучение",
  last_name: "Фамилия",
  first_name: "Имя",
  patronymic: "Отчество",
  email: "Email",
  birth_date: "Дата рождения",
  phone: "Контактный телефон",
  institution: "Учебное заведение",
  education_level: "Уровень образования",
  education_document_received: "Документ об образовании уже получен",
  education_document_name: "Название документа об образовании",
  education_document_series: "Серия документа",
  education_document_number: "Номер документа",
  education_document_date: "Дата выдачи документа",
};
export const emptyLearner: LearnerData = {
  last_name: "",
  first_name: "",
  patronymic: "",
  email: "",
  birth_date: null,
  phone: "",
  institution: "",
  education_level: "",
  education_document_received: false,
  education_document_name: "",
  education_document_series: "",
  education_document_number: "",
  education_document_date: null,
  passport_series: "", passport_number: "", passport_issued_by: "", passport_issued_on: null,
  passport_department_code: "", registration_address: "", residential_address: "", snils: "", inn: "", referral_source: "",
};
export function learnerFieldsOf(source: Partial<LearnerData>): LearnerData {
  return Object.fromEntries(
    Object.entries(emptyLearner).map(([k, v]) => [
      k,
      source[k as keyof LearnerData] ?? v,
    ]),
  ) as LearnerData;
}
export function validateLearner(value: LearnerData): Record<string, string> {
  const errors: Record<string, string> = {};
  const today = new Date().toLocaleDateString("en-CA");
  for (const field of ["birth_date", "education_document_date", "passport_issued_on"] as const)
    if (value[field] && value[field]! > today)
      errors[field] = "Дата не может быть в будущем.";
  if (
    value.birth_date &&
    value.education_document_date &&
    value.education_document_date < value.birth_date
  )
    errors.education_document_date =
      "Дата выдачи не может быть раньше даты рождения.";
  if (
    value.phone &&
    (!/^\+?[\d ()-]+$/.test(value.phone) ||
      value.phone.replace(/\D/g, "").length < 7 ||
      value.phone.replace(/\D/g, "").length > 15)
  )
    errors.phone =
      "Укажите телефон: от 7 до 15 цифр, допустимы +, пробелы, скобки и дефисы.";
  if (value.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.email))
    errors.email = "Укажите корректный email.";
  return errors;
}
export function ErrorBox({
  errors,
}: {
  errors: Record<string, unknown> | null;
}) {
  if (!errors || !Object.keys(errors).length) return null;
  const names: Record<string, string> = {
    ...fieldLabels,
    old_password: "Текущий пароль",
    new_password1: "Новый пароль",
    new_password2: "Подтверждение пароля",
    sequence: "Порядковое число", number_code: "Код ДО / ДПО", realization_year: "Год реализации",
    department: "Шифр подразделения", contract_date: "Дата договора",
    university_representative: "Представитель университета", authority_basis: "Основание полномочий",
    university_email: "Email университета", program_title: "Название программы", program_kind: "Вид программы",
    program_program_kind: "Вид программы", program_study_form: "Форма обучения", program_hours: "Количество часов",
    program_starts_on: "Начало обучения", program_ends_on: "Окончание обучения",
  };
  return (
    <div className="alert error" role="alert">
      <strong>Проверьте данные</strong>
      <ul>
        {Object.entries(errors).map(([key, value]) => (
          <li key={key}>
            {names[key] ? names[key] + ": " : ""}
            {Array.isArray(value) ? value.join(" ") : String(value)}
          </li>
        ))}
      </ul>
    </div>
  );
}
function errorDetails(e: unknown) {
  return e instanceof ApiError
    ? e.details
    : {
        detail:
          "Не удалось выполнить запрос. Введённые данные сохранены в форме.",
      };
}

export function LearnerFields({
  value,
  change,
  disabled = false,
  profile = false,
  requiredFields = [],
  errors = null,
  employee = false,
}: {
  value: LearnerData;
  change: (v: LearnerData) => void;
  disabled?: boolean;
  profile?: boolean;
  requiredFields?: (keyof LearnerData)[];
  errors?: Record<string, unknown> | null;
  employee?: boolean;
}) {
  const documentFields = [
    "education_document_name",
    "education_document_series",
    "education_document_number",
    "education_document_date",
  ];
  return (
    <div className="fields learner-fields">
      {(Object.keys(emptyLearner) as (keyof LearnerData)[]).map((key) => {
        if (
          employee &&
          !["last_name", "first_name", "patronymic", "email", "phone"].includes(
            key,
          )
        )
          return null;
        if (documentFields.includes(key) && !value.education_document_received)
          return null;
        const required = requiredFields.includes(key);
        const id = `${profile ? "profile" : "application"}-${key}`;
        const accessibility = {
          id,
          "aria-invalid": !!errors?.[key],
          "aria-describedby": errors?.[key] ? `${id}-error` : undefined,
        };
        if (key === "education_document_received")
          return (
            <label key={key} className="checkbox full-field">
              <input
                {...accessibility}
                disabled={disabled}
                type="checkbox"
                checked={value[key]}
                onChange={(e) => change({ ...value, [key]: e.target.checked })}
              />
              <span>
                {fieldLabels[key]}
                <small className="field-help">
                  Если вы ещё учитесь, документ об образовании не требуется.
                </small>
              </span>
            </label>
          );
        return (
          <label key={key}>
            {fieldLabels[key]}
            {required && <span className="required-marker"> *</span>}
            {!required && key !== "email" && (
              <small className="optional-marker"> · необязательно</small>
            )}
            {key === "education_level" ? (
              <select
                {...accessibility}
                disabled={disabled}
                value={value[key]}
                onChange={(e) => change({ ...value, [key]: e.target.value })}
              >
                <option value="">Не указано</option>
                {[
                  ["studying", "Обучаюсь"],
                  ["secondary", "Среднее общее"],
                  ["vocational", "Среднее профессиональное"],
                  ["bachelor", "Бакалавриат"],
                  ["specialist", "Специалитет"],
                  ["master", "Магистратура"],
                  ["postgraduate", "Подготовка кадров высшей квалификации"],
                ].map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
            ) : (
              <input
                {...accessibility}
                disabled={disabled || (profile && key === "email")}
                type={
                  key.includes("date") || key === "passport_issued_on"
                    ? "date"
                    : key === "email"
                      ? "email"
                      : key === "phone"
                        ? "tel"
                        : "text"
                }
                value={String(value[key] ?? "")}
                max={
                  key.includes("date") || key === "passport_issued_on"
                    ? new Date().toISOString().slice(0, 10)
                    : undefined
                }
                maxLength={
                  key.includes("address") ? 1000 : key === "passport_issued_by" ? 500 : key === "referral_source" ? 300 :
                  key === "passport_series" ? 4 : key === "passport_number" ? 6 : key === "passport_department_code" ? 7 :
                  key === "snils" ? 14 : key === "inn" ? 12 :
                  key === "institution"
                    ? 300
                    : key === "education_document_name"
                      ? 200
                      : key === "email"
                        ? 254
                        : key === "phone"
                          ? 30
                          : key === "education_document_series"
                            ? 50
                            : key === "education_document_number"
                              ? 100
                              : 150
                }
                onChange={(e) =>
                  change({
                    ...value,
                    [key]: key.includes("date") || key === "passport_issued_on"
                      ? e.target.value || null
                      : e.target.value,
                  })
                }
              />
            )}
            {errors?.[key] != null && (
              <small className="field-error" id={`${id}-error`}>
                {String(errors[key])}
              </small>
            )}
            {profile && key === "email" && (
              <small className="field-help">
                Email используется для входа. Изменение недоступно, пока не
                настроено подтверждение нового адреса.
              </small>
            )}
          </label>
        );
      })}
    </div>
  );
}

export function ProfileEditor({
  user,
  programs,
  documents,
  onDocumentsChanged,
  onSaved,
  onDirty,
  onNavigate,
  onApply,
}: {
  user: Profile;
  programs: Program[];
  documents: ProfileDocument[];
  onDocumentsChanged: (docs: ProfileDocument[]) => void;
  onSaved: (p: Profile) => Promise<void>;
  onDirty: (dirty: boolean) => void;
  onNavigate: (tab: string) => void;
  onApply: (programId: number) => Promise<void>;
}) {
  const employee = user.role === "operator";
  const [value, setValue] = useState(() => learnerFieldsOf(user));
  const [saved, setSaved] = useState(() => learnerFieldsOf(user));
  const [chosen, setChosen] = useState(programs[0]?.id || 0);
  useEffect(() => {
    if (!programs.some((p) => p.id === chosen)) setChosen(programs[0]?.id || 0);
  }, [programs, chosen]);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, unknown> | null>(null);
  const [notice, setNotice] = useState("");
  const dirty = JSON.stringify(value) !== JSON.stringify(saved);
  useEffect(() => {
    onDirty(dirty);
    return () => onDirty(false);
  }, [dirty, onDirty]);
  const program = programs.find((p) => p.id === chosen);
  const requiredFields = employee
    ? (["last_name", "first_name", "email"] as (keyof LearnerData)[])
    : ([
        ...new Set([
          "last_name",
          "first_name",
          "email",
          ...(program?.required_fields || []),
        ]),
      ] as (keyof LearnerData)[]);
  const missing = requiredFields.filter(
    (f) =>
      !(
        f.startsWith("education_document_") &&
        f !== "education_document_received" &&
        !value.education_document_received
      ) && !value[f],
  );
  const missingDocs =
    program?.requirements.filter(
      (r) =>
        r.required &&
        (!r.only_if_graduated || value.education_document_received) &&
        !documents.some((d) => titleKey(d.title) === titleKey(r.title)),
    ) || [];
  const recommended = (
    [
      "birth_date",
      "phone",
      "institution",
      "education_level",
    ] as (keyof LearnerData)[]
  ).filter((f) => !requiredFields.includes(f) && !value[f]);
  function focus(id: string) {
    const input = document.getElementById(id);
    input?.scrollIntoView({ behavior: "smooth", block: "center" });
    input?.focus({ preventScroll: true });
  }
  async function saveProfile() {
    const validation = validateLearner(value);
    if (Object.keys(validation).length) {
      focus(`profile-${Object.keys(validation)[0]}`);
      throw new ApiError(validation);
    }
    const payload = employee
      ? Object.fromEntries(
          ["last_name", "first_name", "patronymic", "email", "phone"].map(
            (k) => [k, value[k as keyof LearnerData]],
          ),
        )
      : value;
    const result = await api<Profile>("profile/", "PATCH", payload);
    setValue(learnerFieldsOf(result));
    setSaved(learnerFieldsOf(result));
    onDirty(false);
    await onSaved(result);
  }
  return (
    <>
      <div className="eyebrow">
        {employee ? "Данные сотрудника" : "Личные данные"}
      </div>
      <h1>Мой профиль</h1>
      <p className="muted">
        {employee
          ? "Контактные данные сотрудника ДПО. Роль назначается администратором."
          : "Заполните профиль один раз: сохранённые сведения и подходящие документы попадут в новую заявку. Перед отправкой проверьте их. Изменения профиля не меняют существующие заявки."}
      </p>
      {employee && (
        <p className="info-line">
          Роль: Оператор ·{" "}
          <button
            className="text-button"
            onClick={() => onNavigate("security")}
          >
            Настройки безопасности
          </button>
        </p>
      )}
      {!employee && (
        <section
          className="panel profile-panel readiness"
          aria-label="Готовность к подаче"
        >
          <h2>Подготовьте профиль к подаче заявки</h2>
          {program ? (
            <>
              <label>
                Выбранная программа
                <select
                  value={chosen}
                  onChange={(e) => setChosen(Number(e.target.value))}
                >
                  {programs.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title}
                    </option>
                  ))}
                </select>
              </label>
              {!!missing.length && (
                <>
                  <p>Нужно заполнить сведения:</p>
                  <div className="readiness-links">
                    {missing.map((f) => (
                      <button
                        className="text-button"
                        key={f}
                        onClick={() => focus(`profile-${f}`)}
                      >
                        {fieldLabels[f]} →
                      </button>
                    ))}
                  </div>
                </>
              )}
              {!!missingDocs.length && (
                <>
                  <p>Нужно добавить документы:</p>
                  <div className="readiness-links">
                    {missingDocs.map((r) => (
                      <button
                        className="text-button"
                        key={r.id}
                        onClick={() => focus(documentAnchor(r.title))}
                      >
                        {r.title} →
                      </button>
                    ))}
                  </div>
                </>
              )}
              {!!recommended.length && (
                <>
                  <p className="hint">
                    Можно дополнить профиль для будущих заявок — для выбранной
                    программы это необязательно:
                  </p>
                  <div className="readiness-links">
                    {recommended.map((f) => (
                      <button
                        className="text-button"
                        key={f}
                        onClick={() => focus(`profile-${f}`)}
                      >
                        {fieldLabels[f]} →
                      </button>
                    ))}
                  </div>
                </>
              )}
              {!missing.length && !missingDocs.length && (
                <p className="readiness-ok">
                  Данные и документы для выбранной программы заполнены.{" "}
                  {dirty
                    ? "Сохраните изменения перед созданием заявки."
                    : "Можно перейти к выбору программы."}
                </p>
              )}
              <p className="hint">
                Звёздочкой отмечены обязательные при отправке поля выбранной
                программы. Незавершённый профиль можно сохранить.
              </p>
              <button
                className="primary"
                disabled={busy}
                onClick={() => {
                  setErrors(null);
                  setNotice("");
                  setBusy(true);
                  void (async () => {
                    if (dirty) await saveProfile();
                    await onApply(program.id);
                  })()
                    .catch((e) => setErrors(errorDetails(e)))
                    .finally(() => setBusy(false));
                }}
              >
                {busy
                  ? "Подождите…"
                  : dirty
                    ? program.submission_availability.available
                      ? "Сохранить профиль и подать заявку →"
                      : "Сохранить профиль и создать черновик →"
                    : program.submission_availability.available
                      ? "Подать заявку →"
                      : "Создать черновик →"}
              </button>
              <button
                className="secondary"
                onClick={() => onNavigate("programs")}
              >
                К образовательным программам →
              </button>
            </>
          ) : (
            <p className="muted">
              Программы пока не опубликованы. Сохраните контактные данные, чтобы
              подготовиться к подаче.
            </p>
          )}
        </section>
      )}
      <form
        className="panel profile-panel"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          setErrors(null);
          setNotice("");
          setBusy(true);
          void saveProfile()
            .then(() => {
              setNotice("Профиль сохранён.");
            })
            .catch((e) => setErrors(errorDetails(e)))
            .finally(() => setBusy(false));
        }}
      >
        <h2>{employee ? "Данные сотрудника" : "Сведения обучающегося"}</h2>
        <ErrorBox errors={errors} />
        {notice && (
          <div className="alert success" role="status">
            {notice}
          </div>
        )}
        <LearnerFields
          value={value}
          change={setValue}
          disabled={busy}
          profile
          employee={employee}
          requiredFields={requiredFields}
          errors={errors}
        />
        <button className="primary" disabled={busy}>
          {busy ? "Сохраняем…" : "Сохранить изменения"}
        </button>
        {dirty && (
          <span className="save-indicator" role="status">
            Есть несохранённые изменения
          </span>
        )}
      </form>
      {!employee && (
        <ProfileDocuments
          programs={programs}
          documents={documents}
          onChanged={onDocumentsChanged}
        />
      )}
    </>
  );
}

export function SecurityPanel({
  onDirty,
}: {
  onDirty: (dirty: boolean) => void;
}) {
  const [passwords, setPasswords] = useState({
    old_password: "",
    new_password1: "",
    new_password2: "",
  });
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordErrors, setPasswordErrors] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [passwordNotice, setPasswordNotice] = useState("");
  const dirty = Object.values(passwords).some(Boolean);
  useEffect(() => {
    onDirty(dirty);
    return () => onDirty(false);
  }, [dirty, onDirty]);
  return (
    <>
      <div className="eyebrow">Доступ к аккаунту</div>
      <h1>Безопасность</h1>
      <p className="muted">
        После смены пароля текущий сеанс сохранится, остальные завершатся при
        следующем обращении.
      </p>
      <form
        className="panel profile-panel"
        onSubmit={(e) => {
          e.preventDefault();
          setPasswordErrors(null);
          setPasswordNotice("");
          if (passwords.new_password1 !== passwords.new_password2) {
            setPasswordErrors({ new_password2: "Пароли не совпадают." });
            return;
          }
          setPasswordBusy(true);
          void api<{ detail: string }>(
            "auth/password/change/",
            "POST",
            passwords,
          )
            .then((result) => {
              setPasswordNotice(result.detail);
              setPasswords({
                old_password: "",
                new_password1: "",
                new_password2: "",
              });
            })
            .catch((e) => setPasswordErrors(errorDetails(e)))
            .finally(() => setPasswordBusy(false));
        }}
      >
        <h2>Смена пароля</h2>
        <ErrorBox errors={passwordErrors} />
        {passwordNotice && (
          <div className="alert success" role="status">
            {passwordNotice}
          </div>
        )}
        {[
          ["old_password", "Текущий пароль"],
          ["new_password1", "Новый пароль"],
          ["new_password2", "Подтверждение нового пароля"],
        ].map(([key, label]) => (
          <label key={key}>
            {label}
            <input
              type="password"
              required
              autoComplete={
                key === "old_password" ? "current-password" : "new-password"
              }
              value={passwords[key as keyof typeof passwords]}
              onChange={(e) =>
                setPasswords({ ...passwords, [key]: e.target.value })
              }
            />
          </label>
        ))}
        <button className="secondary" disabled={passwordBusy}>
          {passwordBusy ? "Обновляем…" : "Изменить пароль"}
        </button>
      </form>
    </>
  );
}

export function AuthRecovery({
  reset,
  onClose,
}: {
  reset: { uid: string; token: string } | null;
  onClose: () => void;
}) {
  const [email, setEmail] = useState("");
  const [passwords, setPasswords] = useState({
    new_password1: "",
    new_password2: "",
  });
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, unknown> | null>(null);
  const [notice, setNotice] = useState("");
  const [done, setDone] = useState(false);
  return (
    <>
      <div className="eyebrow">Доступ к аккаунту</div>
      <h2>{reset ? "Новый пароль" : "Восстановление доступа"}</h2>
      <ErrorBox errors={errors} />
      {notice && (
        <div className="alert success" role="status">
          {notice}
        </div>
      )}
      {!done && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setErrors(null);
            setBusy(true);
            void api<{ detail: string }>(
              reset ? "auth/password/reset/confirm/" : "auth/password/reset/",
              "POST",
              reset ? { ...reset, ...passwords } : { email },
            )
              .then((r) => {
                setNotice(r.detail);
                setPasswords({ new_password1: "", new_password2: "" });
                setDone(true);
              })
              .catch((e) => setErrors(errorDetails(e)))
              .finally(() => setBusy(false));
          }}
        >
          {reset ? (
            [
              ["new_password1", "Новый пароль"],
              ["new_password2", "Подтверждение пароля"],
            ].map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  type="password"
                  required
                  autoComplete="new-password"
                  value={passwords[key as keyof typeof passwords]}
                  onChange={(e) =>
                    setPasswords({ ...passwords, [key]: e.target.value })
                  }
                />
              </label>
            ))
          ) : (
            <label>
              Email
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
          )}
          <button className="primary full" disabled={busy}>
            {busy
              ? "Подождите…"
              : reset
                ? "Сохранить новый пароль"
                : "Запросить восстановление"}
          </button>
        </form>
      )}
      <button className="text-button full" disabled={busy} onClick={onClose}>
        Вернуться ко входу
      </button>
    </>
  );
}

export function Pager({
  page,
  total,
  busy = false,
  onPage,
}: {
  page: number;
  total: number;
  busy?: boolean;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / 10));
  return (
    <div className="pagination" aria-label="Страницы">
      <span>
        Всего: {total} · Страница {page} из {pages}
      </span>
      <div>
        <button
          className="secondary"
          disabled={busy || page <= 1}
          onClick={() => onPage(page - 1)}
        >
          Назад
        </button>
        <button
          className="secondary"
          disabled={busy || page >= pages}
          onClick={() => onPage(page + 1)}
        >
          Далее
        </button>
      </div>
    </div>
  );
}
export function ApplicationTable({
  items,
  operator,
  busy,
  onOpen,
}: {
  items: Application[];
  operator: boolean;
  busy: boolean;
  onOpen: (id: number) => void;
}) {
  return (
    <div className="table-shell">
      <table className="applications-table">
        <thead>
          <tr>
            <th>Номер заявки</th>
            <th>Программа{operator ? " / обучающийся" : ""}</th>
            <th>Дата</th>
            <th>Статус</th>
            <th>
              <span className="sr-only">Действия</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr key={a.id}>
              <td data-label="Номер заявки">{a.number}</td>
              <td data-label="Программа">
                <strong>{a.program.title}</strong>
                {operator && (
                  <small>
                    {a.last_name} {a.first_name}
                  </small>
                )}
              </td>
              <td data-label="Дата">
                {new Date(a.created_at).toLocaleDateString("ru-RU")}
              </td>
              <td data-label="Статус">
                <span className={"badge " + a.status}>{a.status_label}</span>
              </td>
              <td>
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() => onOpen(a.id)}
                >
                  Открыть<span className="sr-only"> заявку {a.number}</span>
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function DashboardPanel({
  operator,
  onOpen,
  onNavigate,
  onUnread,
}: {
  operator: boolean;
  onOpen: (id: number) => void;
  onNavigate: (tab: string) => void;
  onUnread: (n: number) => void;
}) {
  const [data, setData] = useState<Dashboard | null>(null);
  const [errors, setErrors] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true);
    setErrors(null);
    try {
      const d = await api<Dashboard>("dashboard/");
      setData(d);
      onUnread(d.unread);
    } catch (e) {
      setErrors(errorDetails(e));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  const names: Record<string, string> = {
    draft: "Черновики",
    review: "На проверке",
    accepted: "Приняты",
    rejected: "Отклонены",
  };
  const actions: Record<string, string> = {
    contract_registered: "Договор зарегистрирован",
    created: "Заявка создана",
    submitted: "Отправлена на проверку",
    accepted: "Принята",
    rejected: "Отклонена",
  };
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            {operator ? "Рабочее место оператора" : "Личный кабинет"}
          </div>
          <h1>Главная</h1>
          <p className="muted">
            {operator
              ? "Заявки, ожидающие решения, и последние события."
              : "Ваши заявки и результаты рассмотрения."}
          </p>
        </div>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => void load()}
        >
          Обновить
        </button>
      </div>
      <ErrorBox errors={errors} />
      {busy && !data && <p role="status">Загружаем данные…</p>}
      {data && (
        <>
          <div className="stats-grid">
            {Object.entries(data.counts)
              .filter(([key]) => !operator || key !== "draft")
              .map(([key, value]) => (
                <button
                  key={key}
                  className="stat-card"
                  onClick={() => onNavigate("applications")}
                >
                  <span>{names[key]}</span>
                  <strong>{value}</strong>
                </button>
              ))}
          </div>
          <div className="summary-links">
            <button
              className="text-button"
              onClick={() => onNavigate("notifications")}
            >
              Непрочитанных уведомлений: {data.unread}
            </button>
            {!operator && (
              <button
                className="text-button"
                onClick={() => onNavigate("programs")}
              >
                Выбрать программу →
              </button>
            )}
          </div>
          <section className="panel">
            <h2>Последние события</h2>
            {data.events.length ? (
              <ol className="activity-list">
                {data.events.map((event) => (
                  <li key={event.id}>
                    <div>
                      <button
                        className="text-button"
                        onClick={() => onOpen(event.application)}
                      >
                        {event.number}
                      </button>
                      <strong>{actions[event.action]}</strong>
                      {event.reason && <p className="reason">{event.reason}</p>}
                      <small>
                        {event.actor_name} ·{" "}
                        {new Date(event.created_at).toLocaleString("ru-RU")}
                      </small>
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="muted">Событий пока нет.</p>
            )}
          </section>
        </>
      )}
    </>
  );
}
export function NotificationsPanel({
  onOpen,
  onUnread,
}: {
  onOpen: (id: number) => void;
  onUnread: (n: number) => void;
}) {
  const [data, setData] = useState<Page<Notification> | null>(null);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, unknown> | null>(null);
  async function load(p = page) {
    setBusy(true);
    setErrors(null);
    try {
      setData(await api<Page<Notification>>(`notifications/?page=${p}`));
      setPage(p);
      const d = await api<Dashboard>("dashboard/");
      onUnread(d.unread);
    } catch (e) {
      setErrors(errorDetails(e));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void load(1);
  }, []);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">Изменения по заявкам</div>
          <h1>Уведомления</h1>
        </div>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => void load()}
        >
          Обновить
        </button>
      </div>
      <ErrorBox errors={errors} />
      {busy && !data && <p role="status">Загружаем уведомления…</p>}
      {data?.results.map((n) => (
        <article
          className={"panel notification " + (!n.read_at ? "unread" : "")}
          key={n.id}
        >
          <span className="notification-state">
            {n.read_at ? "Прочитано" : "Новое"}
          </span>
          <h2>{n.text}</h2>
          <p className="hint">
            {new Date(n.created_at).toLocaleString("ru-RU")}
          </p>
          <div className="button-row">
            <button
              className="text-button"
              disabled={busy}
              onClick={() => onOpen(n.application)}
            >
              Открыть заявку
            </button>
            {!n.read_at && (
              <button
                className="secondary"
                disabled={busy}
                onClick={() => {
                  setBusy(true);
                  void api(`notifications/${n.id}/read/`, "POST")
                    .then(() => load())
                    .catch((e) => {
                      setErrors(errorDetails(e));
                      setBusy(false);
                    });
                }}
              >
                Отметить прочитанным
              </button>
            )}
          </div>
        </article>
      ))}
      {data && !data.results.length && (
        <div className="empty">Уведомлений пока нет.</div>
      )}
      {data && (
        <Pager
          page={page}
          total={data.count}
          busy={busy}
          onPage={(p) => void load(p)}
        />
      )}
    </>
  );
}
export function DocumentsPanel({ onOpen }: { onOpen: (id: number) => void }) {
  const [data, setData] = useState<Page<Application> | null>(null);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, unknown> | null>(null);
  async function load(p: number) {
    setBusy(true);
    setErrors(null);
    try {
      setData(await api<Page<Application>>(`documents/?page=${p}`));
      setPage(p);
    } catch (e) {
      setErrors(errorDetails(e));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void load(1);
  }, []);
  const grouped = new Map<string, Application[]>();
  for (const app of data?.results || []) {
    const key = app.program.title;
    grouped.set(key, [...(grouped.get(key) || []), app]);
  }
  return (
    <>
      <div className="eyebrow">Прикреплённые файлы</div>
      <h1>Мои документы</h1>
      <p className="muted">
        Документы сгруппированы по программе и заявке. Доступ проверяется при
        каждом открытии.
      </p>
      <ErrorBox errors={errors} />
      {busy && <p role="status">Загружаем документы…</p>}
      {[...grouped].map(([title, apps]) => (
        <section className="panel" key={title}>
          <h2>{title}</h2>
          {apps.map((app) => (
            <div className="document-group" key={app.id}>
              <button className="text-button" onClick={() => onOpen(app.id)}>
                {app.number} · {app.status_label}
              </button>
              {app.documents.map((d) => (
                <div className="document" key={d.id}>
                  <strong>{d.original_name}</strong>
                  <div className="button-row">
                    <a href={d.preview_url} target="_blank" rel="noreferrer">
                      Просмотреть
                    </a>
                    <a href={d.download_url}>Скачать</a>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </section>
      ))}
      {data && !data.results.length && (
        <div className="empty">
          Прикреплённых документов пока нет. Добавьте файлы в черновик заявки.
        </div>
      )}
      {data && (
        <Pager
          page={page}
          total={data.count}
          busy={busy}
          onPage={(p) => void load(p)}
        />
      )}
    </>
  );
}
