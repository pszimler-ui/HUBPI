// A providerlista kirajzolása a /api/providers válaszából.
// `box` a konténer elem, `selected` egy Set a kiválasztott providerekkel.
function renderProviders(data, box, selected) {
  box.replaceChildren();
  data.providers.forEach(p => {
    const el = document.createElement('span');
    el.className = 'provider';
    el.textContent = `${p.name} (${p.model})`;

    if (p.limited) {
      const badge = document.createElement('small');
      badge.className = 'badge-limited';
      badge.textContent = ' Limited access';
      el.appendChild(badge);
      el.title = 'Korlátozott hozzáférésű provider';
    }

    if (p.ready) {
      el.onclick = () => {
        if (selected.has(p.name)) { selected.delete(p.name); el.classList.remove('active'); }
        else { selected.add(p.name); el.classList.add('active'); }
      };
    } else {
      el.style.opacity = 0.4;
      el.style.cursor = 'not-allowed';
      el.title = 'Nincs API kulcs a .env-ben';
    }
    box.appendChild(el);
  });
}
