import { useState } from "react";
import { api, ApiError, type ProfileDocument, type Program } from "./api";

export const titleKey = (title: string) =>
  title.trim().replace(/\s+/g, " ").toLowerCase();
export const documentAnchor = (title: string) =>
  "profile-doc-" +
  Array.from(titleKey(title))
    .map((c) => c.codePointAt(0)!.toString(16))
    .join("-");

export function ProfileDocuments({
  programs,
  documents,
  onChanged,
}: {
  programs: Program[];
  documents: ProfileDocument[];
  onChanged: (documents: ProfileDocument[]) => void;
}) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<{ title: string; message: string } | null>(
    null,
  );
  const [notice, setNotice] = useState("");
  const titles = [
    ...new Map(
      [
        ...programs.flatMap((p) => p.requirements.map((r) => r.title)),
        ...documents.map((d) => d.title),
      ].map((title) => [titleKey(title), title]),
    ).values(),
  ];
  async function update(title: string, action: () => Promise<unknown>) {
    setBusy(title);
    setError(null);
    setNotice("");
    try {
      await action();
      onChanged(await api<ProfileDocument[]>("profile/documents/"));
      setNotice(
        "Документы профиля сохранены. Копии в существующих заявках остаются прежними.",
      );
    } catch (e) {
      setError({
        title,
        message:
          e instanceof ApiError
            ? Object.values(e.details).flat().join(" ")
            : "Не удалось сохранить документ. Повторите попытку.",
      });
    } finally {
      setBusy("");
    }
  }
  return (
    <section className="panel profile-panel" id="profile-documents">
      <h2>Документы профиля</h2>
      <p className="hint">
        Загрузите файл один раз. При создании заявки подставится последняя
        версия с тем же назначением. В черновике можно выбрать другую версию или
        загрузить новый файл. PDF, JPEG или PNG до 10 МБ.
      </p>
      {notice && (
        <p className="alert success" role="status">
          {notice}
        </p>
      )}
      {!titles.length && (
        <p className="empty">
          Требования к документам появятся вместе с образовательными
          программами.
        </p>
      )}
      {titles.map((title) => (
        <div className="document" key={titleKey(title)}>
          <h3>{title}</h3>
          <p className="hint">
            Обязательность определяется выбранной программой. Для ещё
            обучающихся документ об образовании может не требоваться.
          </p>
          {documents
            .filter((d) => titleKey(d.title) === titleKey(title))
            .map((d, i) => (
              <div key={d.id} className="profile-document-version">
                <strong>{d.original_name}</strong>
                <small>
                  {i === 0 ? "Последняя версия · " : "Предыдущая версия · "}
                  {new Date(d.uploaded_at).toLocaleString("ru-RU")} ·{" "}
                  {Math.ceil(d.size / 1024)} КБ
                </small>
                <div className="button-row">
                  <a href={d.preview_url} target="_blank" rel="noreferrer">
                    Просмотреть
                  </a>
                  <a href={d.download_url}>Скачать</a>
                  <button
                    className="text-button"
                    disabled={!!busy}
                    onClick={() => {
                      if (
                        window.confirm(
                          "Удалить документ из профиля? Копии в заявках сохранятся.",
                        )
                      )
                        void update(title, () =>
                          api(`profile/documents/${d.id}/`, "DELETE"),
                        );
                    }}
                  >
                    Удалить из профиля
                  </button>
                </div>
              </div>
            ))}
          {!documents.some((d) => titleKey(d.title) === titleKey(title)) && (
            <p className="muted">Файл ещё не добавлен</p>
          )}
          <label className="upload-label">
            {busy === title ? "Сохраняем документ…" : `Добавить файл: ${title}`}
            <input
              id={documentAnchor(title)}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png"
              disabled={!!busy}
              aria-invalid={error?.title === title}
              aria-describedby={
                error?.title === title
                  ? documentAnchor(title) + "-error"
                  : undefined
              }
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                const form = new FormData();
                form.append("file", file);
                form.append("title", title);
                // Keep the selected filename on failure so the user can retry.
                void update(title, () =>
                  api("profile/documents/", "POST", form),
                );
              }}
            />
          </label>
          {error?.title === title && (
            <p
              className="field-error"
              id={documentAnchor(title) + "-error"}
              role="alert"
            >
              {error.message}
            </p>
          )}
        </div>
      ))}
    </section>
  );
}
