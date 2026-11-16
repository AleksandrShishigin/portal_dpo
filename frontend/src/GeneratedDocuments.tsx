import { useEffect, useState } from "react";
import { api, ApiError, type Application, type LearnerData, type Program, type Page } from "./api";
import { ErrorBox, LearnerFields, Pager, learnerFieldsOf } from "./CabinetPanels";

type Contract = { id: number; number: string; date: string; applicant: string; program_title: string;
  application: number; application_number: string; download_url: string;
  signature_status: "unsigned" | "pending" | "failed" | "signed"; signature_status_label: string;
  signed_at: string | null; signed_pdf_download_url: string | null };
type ContractData = { student: LearnerData; program: Program; sequence: string | number;
  number_code: string; realization_year: string; department: string; contract_date: string;
  university_representative: string; authority_basis: string; university_email: string };
type Draft = { data?: ContractData; preview_number?: string; errors?: Record<string, unknown>; warning?: string;
  registered: Contract | null };
const details = (e: unknown) => e instanceof ApiError ? e.details : { detail: "Не удалось выполнить запрос. Повторите попытку." };

export function StatementDocument({ app, unsaved = false }: { app: Application; unsaved?: boolean }) {
  const doc = app.statement_document;
  const errors = Object.values(doc.errors).flat().map(String);
  const available = doc.saved || (app.status === "draft" && !errors.length && !unsaved);
  return <section className="panel">
    <h2>Заявление DOCX</h2>
    <p>{doc.saved ? "Сохранено при отправке. Скачивание возвращает исходный файл." : "Перед формированием сохраните данные заявки. При отправке будет сохранён итоговый файл."}</p>
    {doc.warning && <p className="alert" role="note">{doc.warning}</p>}
    {!!errors.length && app.status === "draft" && <div className="hint">Для заявления:<ul>{errors.map((text, i) => <li key={i}>{text}</li>)}</ul></div>}
    {unsaved && <p className="hint">Сохраните изменения заявки перед скачиванием.</p>}
    {available && <a href={doc.download_url}>Скачать {doc.saved ? "заявление" : "черновик заявления"} DOCX</a>}
  </section>;
}

const contractLabels: Record<string, string> = {
  sequence: "Порядковое число", number_code: "Код ДО / ДПО", realization_year: "Год реализации (26/28)",
  department: "Шифр подразделения", contract_date: "Дата договора", university_representative: "Представитель университета (ФИО и должность)",
  authority_basis: "Основание полномочий представителя", university_email: "Email университета",
};
const programLabels: Record<string, string> = { title: "Название программы", program_kind: "Вид программы", study_form: "Форма обучения",
  hours: "Количество часов", starts_on: "Начало обучения", ends_on: "Окончание обучения" };
const choices: Record<string, [string, string][]> = {
  program_kind: [["повышения квалификации", "Повышение квалификации"], ["профессиональной переподготовки", "Профессиональная переподготовка"]],
  study_form: [["1", "Очная — 1"], ["2", "Очно-заочная — 2"], ["3", "Заочная — 3"]],
  number_code: [["О", "ДО — О"], ["Р", "ДПО — Р"]],
};

export function ContractEditor({ app, onDirty }: { app: Application; onDirty: (v: boolean) => void }) {
  const [result, setResult] = useState<Draft | null>(null);
  const [value, setValue] = useState<ContractData | null>(null);
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, unknown> | null>(null);
  const [notice, setNotice] = useState("");
  const path = `applications/${app.id}/contract/`;
  const dirty = !!value && JSON.stringify(value) !== saved;
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  useEffect(() => {
    let cancelled = false;
    setResult(null); setValue(null); setErrors(null);
    api<Draft>(path).then(r => { if (!cancelled) { setResult(r); setValue(r.data ?? null); setSaved(JSON.stringify(r.data)); } })
      .catch(e => { if (!cancelled) setErrors(details(e)); });
    return () => { cancelled = true; };
  }, [path]);
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", handler); return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);
  async function save() {
    const r = await api<Draft>(path, "PATCH", value);
    setResult(r); setValue(r.data ?? null); setSaved(JSON.stringify(r.data)); return r;
  }
  async function perform(fn: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setErrors(null); setNotice("");
    try { await fn(); } catch (e) { setErrors(details(e)); } finally { setBusy(false); }
  }
  if (result?.registered) return <section className="panel"><h2>Договор № {result.registered.number}</h2>
    <p>Зарегистрирован {result.registered.date.split("-").reverse().join(".")}. Данные и файл зафиксированы.</p>
    <a href={result.registered.download_url}>Скачать договор DOCX</a></section>;
  return <section className="panel"><h2>Черновик договора</h2>
    <ErrorBox errors={errors} />
    {result?.warning && <p className="alert" role="note">{result.warning}</p>}
    {!value && <p>Загружаем реквизиты…</p>}
    {value && <>
      <p className="hint">Проверьте данные перед регистрацией. Правки относятся к договору. Подписи и печать остаются незаполненными.</p>
      <h3>Обучающийся</h3>
      <LearnerFields value={learnerFieldsOf(value.student)} change={student => setValue({ ...value, student })} disabled={busy} errors={errors} />
      <h3>Программа и регистрация</h3>
      <div className="fields">
        {Object.entries(programLabels).map(([key, label]) => <label key={key}>{label}
          {choices[key] ? <select disabled={busy} value={String(value.program[key as keyof Program] ?? "")}
            onChange={e => setValue({ ...value, program: { ...value.program, [key]: e.target.value } })}>
            <option value="">Выберите</option>{choices[key].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            : <input disabled={busy} type={key.endsWith("_on") ? "date" : key === "hours" ? "number" : "text"}
              value={String(value.program[key as keyof Program] ?? "")} maxLength={250}
              onChange={e => setValue({ ...value, program: { ...value.program, [key]: key === "hours" ? Number(e.target.value) : e.target.value } })} />}
        </label>)}
        {Object.entries(contractLabels).map(([key, label]) => <label key={key}>{label}
          {choices[key] ? <select disabled={busy} value={String(value[key as keyof ContractData])}
            onChange={e => setValue({ ...value, [key]: e.target.value })}>
            <option value="">Выберите</option>{choices[key].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            : <input disabled={busy} type={key === "contract_date" ? "date" : key === "sequence" ? "number" : key === "university_email" ? "email" : "text"}
              value={String(value[key as keyof ContractData] ?? "")} maxLength={500}
              onChange={e => setValue({ ...value, [key]: e.target.value })} />}
        </label>)}
      </div>
      <p role="status">Предварительный номер: <strong>{dirty ? "сохраните для расчёта сервером" : result?.preview_number || "заполните параметры номера"}</strong></p>
      {result?.errors && !dirty && <ErrorBox errors={result.errors} />}
      {notice && <p role="status">{notice}</p>}
      <div className="button-row">
        <button className="secondary" disabled={busy} onClick={() => void perform(async () => { await save(); setNotice("Черновик сохранён, реквизиты проверены."); })}>Сохранить и проверить</button>
        {!dirty && result?.errors && !Object.keys(result.errors).length && <a href={`${path.startsWith("/") ? "" : "/api/"}${path}download/`}>Скачать черновик DOCX</a>}
        <button className="primary" disabled={busy || dirty || !result?.errors || !!Object.keys(result.errors).length}
          onClick={() => void perform(async () => { const registered = await api<Contract>(`${path}register/`, "POST", {}); setResult({ registered }); setSaved(JSON.stringify(value)); })}>Зарегистрировать договор</button>
      </div>
    </>}
  </section>;
}

export function ContractRegistry({ onOpen }: { onOpen: (id: number) => void }) {
  const [filters, setFilters] = useState<{ signature: "unsigned" | "signed"; search: string; page: number }>({ signature: "unsigned", search: "", page: 1 });
  const [search, setSearch] = useState("");
  const [loaded, setLoaded] = useState<{ key: string; data: Page<Contract> } | null>(null);
  const [errors, setErrors] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const requestKey = JSON.stringify(filters);
  const data = loaded?.key === requestKey ? loaded.data : null;
  useEffect(() => {
    let cancelled = false;
    setBusy(true); setErrors(null); setNotice("");
    const params = new URLSearchParams({ signature: filters.signature, search: filters.search, page: String(filters.page) });
    api<Page<Contract>>(`contracts/?${params}`).then(result => {
      if (!cancelled) setLoaded({ key: requestKey, data: result });
    }).catch(e => { if (!cancelled) setErrors(details(e)); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [requestKey]);
  function selectTab(signature: "unsigned" | "signed") {
    setFilters(current => ({ ...current, signature, page: 1 }));
  }
  return <><div className="eyebrow">Документы ДПО</div><h1>Реестр договоров</h1><ErrorBox errors={errors} />
    <div className="registry-tabs" role="tablist" aria-label="Подписание договоров">
      {([["unsigned", "Не подписанные"], ["signed", "Подписанные"]] as const).map(([signature, label]) =>
        <button key={signature} type="button" role="tab" id={`contract-tab-${signature}`} aria-selected={filters.signature === signature}
          aria-controls="contract-registry-panel" tabIndex={filters.signature === signature ? 0 : -1}
          onClick={() => selectTab(signature)} onKeyDown={e => {
            if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
            e.preventDefault();
            const next = e.key === "Home" ? "unsigned" : e.key === "End" ? "signed" : signature === "unsigned" ? "signed" : "unsigned";
            selectTab(next); document.getElementById(`contract-tab-${next}`)?.focus();
          }}>{label}</button>)}
    </div>
    <form className="filters" onSubmit={e => { e.preventDefault(); setFilters(current => ({ ...current, search: search.trim(), page: 1 })); }}>
      <label>Поиск<input type="search" value={search} maxLength={200} placeholder="Номер договора, ФИО, программа или заявка"
        onChange={e => setSearch(e.target.value)} /></label>
      <button className="secondary" disabled={busy}>Найти</button>
    </form>
    {notice && <p className="info-line" role="status">{notice}</p>}
    <section role="tabpanel" id="contract-registry-panel" aria-labelledby={`contract-tab-${filters.signature}`} aria-busy={busy}>
      {busy && <p role="status">Загружаем договоры…</p>}
      {data?.results.map(c => <article className="panel" key={c.id} data-contract-id={c.id}><h2>{c.number}</h2>
        <p>{c.date.split("-").reverse().join(".")} · {c.applicant}</p><p>{c.program_title}</p>
        {filters.signature === "signed" && c.signed_at && <p>Дата подписания: {new Date(c.signed_at).toLocaleString("ru-RU")}</p>}
        {filters.signature === "unsigned" && <p className="hint">{c.signature_status_label}</p>}
        <div className="button-row"><button className="text-button" onClick={() => onOpen(c.application)}>Заявка {c.application_number}</button>
          <a href={c.download_url}>Скачать DOCX</a>
          {filters.signature === "unsigned" ? <button className="secondary" type="button" aria-label={`Подписать договор ${c.number}`}
            onClick={() => setNotice("Подписание станет доступно после подключения сервиса электронной подписи")}>Подписать</button>
            : c.signed_pdf_download_url && <a href={c.signed_pdf_download_url}>Скачать подписанный PDF</a>}
        </div></article>)}
      {data && !data.count && <p className="empty">{filters.search ? "Договоры по вашему запросу не найдены." :
        filters.signature === "signed" ? "Подписанных договоров пока нет." : "Не подписанных договоров пока нет."}</p>}
      {data && <Pager page={filters.page} total={data.count} busy={busy} onPage={page => setFilters(current => ({ ...current, page }))} />}
    </section></>;
}

export function ProgramDocumentSettings({ programs, onSaved }: { programs: Program[]; onSaved: (p: Program) => void }) {
  const [selected, setSelected] = useState(programs[0]?.id || 0);
  const program = programs.find(p => p.id === selected);
  const [kind, setKind] = useState(program?.program_kind || "");
  const [form, setForm] = useState(program?.study_form || "");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, unknown> | null>(null);
  const [notice, setNotice] = useState("");
  useEffect(() => { setKind(program?.program_kind || ""); setForm(program?.study_form || ""); }, [program]);
  return <section className="panel"><h1>Реквизиты программ для документов</h1>
    <p>Укажите вид программы для заявлений и форму обучения для договоров. Сохранённые документы и отправленные заявки сохраняют прежние данные.</p>
    <ErrorBox errors={errors} /><div className="fields"><label>Программа<select value={selected} onChange={e => { setSelected(Number(e.target.value)); setNotice(""); }}>
      {programs.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
      <label>Вид программы<select value={kind} onChange={e => setKind(e.target.value)}><option value="">Не указан</option>
        {choices.program_kind.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      <label>Форма обучения<select value={form} onChange={e => setForm(e.target.value)}><option value="">Не указана</option>
        {choices.study_form.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label></div>
    <button className="primary" disabled={busy || !program} onClick={async () => { setBusy(true); setErrors(null); setNotice("");
      try { onSaved(await api<Program>(`programs/${selected}/document-settings/`, "PATCH", { program_kind: kind, study_form: form })); setNotice("Реквизиты программы сохранены."); }
      catch(e) { setErrors(details(e)); } finally { setBusy(false); } }}>Сохранить реквизиты</button>
    {notice && <p role="status">{notice}</p>}
  </section>;
}
