/**
 * BrainTrash.gs — служебное удаление (в корзину) файлов ТОЛЬКО внутри Brain-папки.
 * Защита: файл удаляется лишь если его родитель = BRAIN_FOLDER (иначе not_in_brain, без удаления).
 * Trash (setTrashed) обратим (корзина Drive ~30 дней). Аудит — чёрный ящик 4.1 (client-side log_write).
 * Зона: housekeeping Brain (НЕ Лист1/CRM). Вызывается точечно по id, по «да» Филиппа.
 */
var BRAIN_FOLDER_ID = '1uWqHsxk7aEWoSNqaUBMmqkYOh2UKYLkY';

function trashBrainFile_(body) {
  var p = body || {};
  var id = String(p.id || '').trim();
  if (!id) return { ok: false, error: 'no_id' };
  try {
    var f = DriveApp.getFileById(id);
    var title = f.getName();
    // ЗАЩИТА: удаляем ТОЛЬКО файлы, лежащие в Brain-папке.
    var inBrain = false;
    var parents = f.getParents();
    while (parents.hasNext()) {
      if (parents.next().getId() === BRAIN_FOLDER_ID) { inBrain = true; break; }
    }
    if (!inBrain) return { ok: false, error: 'not_in_brain', id: id, title: title };
    if (f.isTrashed()) return { ok: true, id: id, title: title, already_trashed: true };
    f.setTrashed(true);
    return { ok: true, id: id, title: title, trashed: true };
  } catch (err) {
    return { ok: false, error: 'trash_failed', id: id, message: String(err) };
  }
}

/**
 * Переместить файл из Brain-папки в подпапку Brain/_archive (обратимо — файл цел, лишь сменил родителя).
 * Защита: двигаем ТОЛЬКО файл, лежащий ПРЯМО в Brain-папке (иначе not_in_brain). Подпапка создаётся при
 * первом вызове (getOrCreateFolder_). Зона: housekeeping Brain (НЕ Лист1/CRM). По «да» Филиппа.
 */
function moveBrainFile_(body) {
  var p = body || {};
  var id = String(p.id || '').trim();
  if (!id) return { ok: false, error: 'no_id' };
  var folderName = String(p.folder || '_archive').trim() || '_archive';
  try {
    var f = DriveApp.getFileById(id);
    var title = f.getName();
    var brain = DriveApp.getFolderById(BRAIN_FOLDER_ID);
    // ЗАЩИТА: двигаем ТОЛЬКО файлы, лежащие прямо в Brain-папке.
    var inBrain = false;
    var parents = f.getParents();
    while (parents.hasNext()) {
      if (parents.next().getId() === BRAIN_FOLDER_ID) { inBrain = true; break; }
    }
    if (!inBrain) return { ok: false, error: 'not_in_brain', id: id, title: title };
    var dest = getOrCreateFolder_(brain, folderName);
    f.moveTo(dest);
    return { ok: true, id: id, title: title, moved_to: dest.getId(), folder: folderName };
  } catch (err) {
    return { ok: false, error: 'move_failed', id: id, message: String(err) };
  }
}
