"""Independent DOM projections for in-memory school-read qualification."""

AGENDA_DOM = r"""() => [...document.querySelectorAll('div.kalendarz-dzien')].map(d => {
 const events = [...d.querySelectorAll('tr')].map(r => {
   const c = r.querySelector(':scope > td');
   const s = c.querySelector('span');
   const ids = [c,...c.querySelectorAll('[onclick]')].flatMap(n =>
    [...(n.getAttribute('onclick')||'').matchAll(
     /['"]\/terminarz\/szczegoly\/([0-9]+)['"]/g)].map(m=>m[1]));
   const t = document.createElement('div');
   t.innerHTML = c.getAttribute('title') || '';
   document.body.appendChild(t); const tooltip = t.innerText; t.remove();
   return {text:c.innerText,subject:s?s.innerText:null,
    tooltip,reference:ids[0]||null};
  });
 return {day:Number(d.querySelector('div.kalendarz-numer-dnia').innerText),events};
})"""

DETAIL_DOM = """() => [...document.querySelectorAll('div.container-background tr')]
 .map(r=>({header:!!r.closest('thead'),cells:[...r.children].map(c=>c.innerText)}))"""

HOMEWORK_DOM = """() => ({
 empty:document.querySelectorAll('p.msgEmptyTable').length,
 rows:[...document.querySelectorAll('table.myHomeworkTable tr.line0,'+
  'table.myHomeworkTable tr.line1')].map(r=>[...r.children].map(c=>c.innerText))
})"""

LESSONS_DOM = r"""() => ({
 pagination:[...document.querySelectorAll('div.pagination > span')]
  .map(n=>n.innerText),
 empty:document.querySelectorAll('.msgEmptyTable').length,
 rows:[...document.querySelectorAll('table.decorated tr')]
  .filter(r=>!r.closest('thead')).map(r=>({
   cells:[...r.children].map(c=>({text:c.innerText,
    day:c.classList.contains('center')&&c.classList.contains('small'),
    weekday:c.classList.contains('tiny')})),
   references:[...r.querySelectorAll('a[onclick]')].flatMap(a=>
    [...a.getAttribute('onclick').matchAll(
     /['"]\/przegladaj_nb\/szczegoly\/([0-9]+)['"]/g)].map(m=>m[1]))
  }))
})"""

NOTES_DOM = """() => ({
 empty:[...document.querySelectorAll('p.msgEmptyTable')].filter(n=>
  n.innerText.trim().includes('Brak uwag')).length,
 tables:[...document.querySelectorAll('table.decorated')].map(t=>({
  header:[...t.querySelectorAll('thead th,thead td')].map(c=>c.innerText),
  rows:[...t.querySelectorAll('tr')].filter(r=>!r.closest('thead'))
   .map(r=>[...r.children].map(c=>c.innerText))
 }))
})"""
