export type LearnerData = {
  passport_series: string;
  passport_number: string;
  passport_issued_by: string;
  passport_issued_on: string | null;
  passport_department_code: string;
  registration_address: string;
  residential_address: string;
  snils: string;
  inn: string;
  referral_source: string;
  last_name: string;
  first_name: string;
  patronymic: string;
  email: string;
  birth_date: string | null;
  phone: string;
  institution: string;
  education_level: string;
  education_document_received: boolean;
  education_document_name: string;
  education_document_series: string;
  education_document_number: string;
  education_document_date: string | null;
};
export type Profile = Partial<LearnerData> & {
  id: number;
  last_name: string;
  first_name: string;
  patronymic: string;
  email: string;
  phone: string;
  role: "student" | "operator";
};
export type Requirement = {
  id: number;
  title: string;
  required: boolean;
  only_if_graduated: boolean;
};
export type Program = {
  program_kind: string;
  study_form: string;
  id: number;
  title: string;
  description: string;
  starts_on: string;
  ends_on: string;
  hours: number;
  lms_url: string;
  requirements: Requirement[];
  required_fields: (keyof LearnerData)[];
  profile_missing_fields?: { field: string; label: string }[];
  submission_availability: Availability;
};
export type Availability = {
  available: boolean;
  code: string;
  reason: string;
  next_step: string;
};
export type ProfileDocument = {
  id: number;
  title: string;
  original_name: string;
  preview_url: string;
  download_url: string;
  uploaded_at: string;
  size: number;
};
export type Attachment = {
  id: number;
  requirement: number;
  original_name: string;
  download_url: string;
  preview_url: string;
  size: number;
  source_profile_document: number | null;
};
export type Application = LearnerData & {
  statement_document: { saved: boolean; download_url: string; warning: string; errors: Record<string, unknown> };
  contract_document: { number: string; date: string; download_url: string } | null;
  id: number;
  number: string;
  program: Program;
  last_name: string;
  first_name: string;
  patronymic: string;
  email: string;
  status: string;
  status_label: string;
  consent_at: string | null;
  consent_version: string;
  created_at: string;
  updated_at: string;
  missing_fields: { field: string; label: string }[];
  missing_documents: { id: number; title: string }[];
  submission_availability: Availability;
  submission_snapshot: {
    consent?: { text: string; version: string; accepted_at: string };
    legacy_reconstructed?: boolean;
  };
  decision_reason: string;
  documents: Attachment[];
  events: {
    id: number;
    action: string;
    actor_name: string;
    created_at: string;
    reason: string;
  }[];
};
export type Consent = {
  version: string;
  text: string;
  available: boolean;
  kind?: "demo_confirmation" | "personal_data" | "prototype";
};
export type Page<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
export type Notification = {
  id: number;
  application: number;
  kind: string;
  text: string;
  created_at: string;
  read_at: string | null;
};
export type Dashboard = {
  counts: Record<string, number>;
  total: number;
  unread: number;
  events: {
    id: number;
    action: string;
    actor_name: string;
    created_at: string;
    application: number;
    number: string;
    reason: string;
  }[];
};
let csrfToken = "";
export class ApiError extends Error {
  constructor(public details: Record<string, unknown>) {
    super("Проверьте введённые данные.");
  }
}
export async function api<T>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  const form = data instanceof FormData;
  let response: Response;
  try {
    response = await fetch("/api/" + path, {
      method,
      credentials: "same-origin",
      headers: {
        ...(data && !form ? { "Content-Type": "application/json" } : {}),
        ...(method !== "GET" ? { "X-CSRFToken": csrfToken } : {}),
      },
      body: data
        ? ((form ? data : JSON.stringify(data)) as BodyInit)
        : undefined,
    });
  } catch {
    throw new ApiError({
      detail:
        "Сервер недоступен. Проверьте, что Django запущен, и повторите действие.",
    });
  }
  const result = await response.json().catch(() => ({
    detail: "Не удалось обработать ответ сервера. Повторите позже.",
  }));
  if (!response.ok) throw new ApiError(result);
  if (path === "session/" && result.apiVersion !== 2) {
    throw new ApiError({
      detail:
        "Для работы с заявками требуется перезапуск обновлённого портала. После перезапуска обновите страницу.",
    });
  }
  if (result.csrfToken) csrfToken = result.csrfToken;
  return result as T;
}
