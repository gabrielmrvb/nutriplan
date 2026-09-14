(() => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const all = [...document.querySelectorAll('body *')].filter(vis);
  const cs = el => getComputedStyle(el);
  const sizes = {}, weights = {}, radii = {};
  let bordered = 0, borderedList = {}, shadowed = 0, upper = 0, upperList = [], cards = document.querySelectorAll('.card').length;
  const bgs = {};
  for (const el of all) {
    const s = cs(el);
    if (el.textContent.trim() && [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) {
      sizes[s.fontSize] = (sizes[s.fontSize] || 0) + 1;
      weights[s.fontWeight] = (weights[s.fontWeight] || 0) + 1;
      if (s.textTransform === 'uppercase') { upper++; upperList.push(el.textContent.trim().slice(0, 30)); }
    }
    const bw = parseFloat(s.borderTopWidth);
    const bc = s.borderTopColor;
    if (bw > 0 && bc !== 'rgba(0, 0, 0, 0)' && s.borderTopStyle !== 'none') { bordered++; borderedList[el.className.baseVal || el.className || el.tagName] = (borderedList[el.className || el.tagName] || 0) + 1; }
    if (s.boxShadow !== 'none') shadowed++;
    const r = s.borderTopLeftRadius; if (r !== '0px') radii[r] = (radii[r] || 0) + 1;
    if (s.backgroundColor !== 'rgba(0, 0, 0, 0)') bgs[s.backgroundColor] = (bgs[s.backgroundColor] || 0) + 1;
  }
  const h1 = document.querySelector('h1'); const h2s = [...document.querySelectorAll('h2')].filter(vis);
  const btns = [...document.querySelectorAll('.btn, button, a.btn')].filter(vis);
  const btnKinds = {};
  for (const b of btns) { const k = cs(b).backgroundColor + '|' + cs(b).color; btnKinds[k] = (btnKinds[k] || 0) + 1; }
  return {
    url: location.pathname,
    pageH: document.documentElement.scrollHeight,
    cards, bordered, borderedTop: Object.entries(borderedList).sort((a,b)=>b[1]-a[1]).slice(0,8),
    shadowed, upper, upperList: upperList.slice(0, 20),
    h1: h1 ? { txt: h1.textContent.trim().slice(0,40), size: cs(h1).fontSize, w: cs(h1).fontWeight, ls: cs(h1).letterSpacing } : null,
    h2: h2s.map(h => cs(h).fontSize + '/' + cs(h).fontWeight),
    sizes: Object.entries(sizes).sort((a,b)=>b[1]-a[1]), weights: Object.entries(weights).sort((a,b)=>b[1]-a[1]),
    radii, bgs: Object.entries(bgs).sort((a,b)=>b[1]-a[1]).slice(0,8), btns: btns.length, btnKinds
  };
})()
