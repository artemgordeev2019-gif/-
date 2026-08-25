/* Подключение общей базы.
 *
 * Пока поля пустые, сайт работает по-старому: показывает данные из
 * data/state.json, а правки держит в памяти браузера, только у вас.
 *
 * Чтобы правки видели все: Supabase → Project Settings → Data API,
 * скопировать Project URL и ключ anon (он публичный, его не прячут —
 * доступ ограничен политиками RLS из site/db/schema.sql).
 */
window.HB_CONFIG = {
  supabaseUrl: "",
  supabaseAnonKey: ""
};
