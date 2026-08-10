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

/**
 * Перенести существующий KB_*-файл В КОРЕНЬ папки Brain (НАРУЖУ→ВНУТРЬ).
 * Зачем отдельно от moveBrainFile_: тот двигает только то, что УЖЕ лежит в Brain, и только в
 * ПОДПАПКУ (страж not_in_brain на входе + getOrCreateFolder_ на выходе). Обратного направления
 * у моста не было вообще, поэтому живые Brain-доки, созданные штабом вне папки, реестром не
 * видятся: register_brain_doc отбивает их тем же not_in_brain.
 * Защита: только файлы с именем KB_* (не тащим в мозг случайное), идемпотентность (уже в Brain →
 * no-op). moveTo делает Brain ЕДИНСТВЕННЫМ родителем — прежняя папка файл теряет. body: { id }.
 */
function moveIntoBrain_(body) {
  var p = body || {};
  var id = String(p.id || '').trim();
  if (!id) return { ok: false, error: 'no_id' };
  try {
    var f = DriveApp.getFileById(id);
    var title = f.getName();
    if (title.indexOf('KB_') !== 0) return { ok: false, error: 'not_kb_file', id: id, title: title };
    var parents = [], ps = f.getParents();
    while (ps.hasNext()) parents.push(ps.next());
    for (var i = 0; i < parents.length; i++) {
      if (parents[i].getId() === BRAIN_FOLDER_ID) {
        return { ok: true, id: id, title: title, already_in_brain: true };
      }
    }
    var was = parents.map(function (x) { return x.getName(); }).join(' | ');
    f.moveTo(DriveApp.getFolderById(BRAIN_FOLDER_ID));   // КОРЕНЬ Brain, не _archive
    return { ok: true, id: id, title: title, moved_from: was || '(без родителя)',
             moved_to: BRAIN_FOLDER_ID, into_brain: true };
  } catch (err) {
    return { ok: false, error: 'move_failed', id: id, message: String(err) };
  }
}

/**
 * СНЯТЬ ключ из BRAIN_MANIFEST (единственная операция реестра, которой у моста не было:
 * setupBrain/registerBrainDoc_/createBrainPlain_/migrateJournalToPlain_ ключи только добавляют
 * или перевешивают, а Script Properties снаружи не правятся — REST-эндпоинта свойств у Apps
 * Script API нет). Мержит: трогает РОВНО один ключ, остальные пары остаются как есть.
 * ОДНОСТОРОННЯЯ: вернуть ключ на удалённый файл нельзя (registerBrainDoc_ требует существующий
 * файл), поэтому нужен явный confirm:true. folder_id защищён — без него ослепнет весь канал.
 * body: { name, confirm:true }.
 */
function unregisterBrainDoc_(body) {
  var p = body || {};
  var name = String(p.name == null ? '' : p.name).trim();
  if (!name) return { ok: false, error: 'need_name' };
  if (name === 'folder_id') {
    return { ok: false, error: 'protected', message: 'folder_id — адрес папки Brain, не снимаем' };
  }
  if (p.confirm !== true) {
    return { ok: false, error: 'need_confirm', name: name,
             message: 'операция односторонняя: нужен confirm:true' };
  }
  var man = getBrainManifest_();
  var before = Object.keys(man).length;
  if (!(name in man)) {
    return { ok: true, name: name, already_absent: true, total: before };
  }
  var oldId = man[name];
  delete man[name];
  PropertiesService.getScriptProperties().setProperty(BRAIN_PROP_KEY, JSON.stringify(man));
  return { ok: true, name: name, removed_id: oldId, unregistered: true,
           total_before: before, total: Object.keys(man).length };
}
