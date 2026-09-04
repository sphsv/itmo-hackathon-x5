from __future__ import annotations

import json
from pathlib import Path


HTML = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Растём вместе — PoC</title>
<style>
:root{--green:#00a34f;--ink:#202522;--muted:#66706a;--bg:#f3f6f4}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font:16px system-ui;color:var(--ink)}
.app{max-width:430px;margin:auto;min-height:100vh;background:white;padding:20px}
h1{font-size:27px;margin:8px 0}.lead{color:var(--muted);margin-top:0}
.switch{display:flex;gap:8px;margin:18px 0}.switch button,.nav button{border:0;border-radius:12px;padding:11px;background:#e8eee9}
.switch button.active,.nav button.active{background:var(--green);color:white}
.card{background:#f5f7f5;border-radius:20px;padding:20px;margin:15px 0}.metric{font-size:42px;font-weight:750;color:var(--green)}
.screen{display:none}.screen.active{display:block}.nav{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;position:sticky;bottom:8px}
.nav button{font-size:12px;padding:10px 4px}.tag{display:inline-block;background:#ddf5e7;color:#08783d;border-radius:99px;padding:5px 9px;margin:3px}
ul{padding-left:20px}.small{font-size:13px;color:var(--muted)}
</style>
</head>
<body><main class="app">
<h1>Растём вместе</h1><p class="lead">Работающий прототип на синтетических данных</p>
<div class="switch"><button data-family="family_ivanovy" class="active">Ивановы</button><button data-family="family_dima">Семья Димы</button></div>
<section id="progress" class="screen active"><div class="card"><div class="small">Рост семьи за 8 недель</div><div class="metric" id="growth"></div><p>Покупки превращаются в видимый семейный прогресс.</p></div></section>
<section id="challenge" class="screen"><div class="card"><div class="small">Персональный челлендж</div><h2 id="mechanic"></h2><p id="explanation"></p><div id="categories"></div><p><b>Цель экономии: <span id="target"></span> ₽</b></p></div></section>
<section id="league" class="screen"><div class="card"><div class="small">Лига сопоставимых семей</div><div class="metric">#<span id="rank"></span></div><p>из <span id="members"></span> семей</p><p>До топ-3: покупка примерно на <b><span id="gap"></span> ₽</b></p></div></section>
<section id="receipt" class="screen"><div class="card"><div class="small">Цифровой чек</div><h2>Ростомер: +2 см</h2><p>Веха: привычная корзина недели</p><p>Спасено: 1 продукт</p><p class="small">Макет; кассовая интеграция не реализована.</p></div></section>
<nav class="nav"><button data-screen="progress" class="active">Рост</button><button data-screen="challenge">Цель</button><button data-screen="league">Лига</button><button data-screen="receipt">Чек</button></nav>
</main>
<script>
const DATA=__DATA__;let family="family_ivanovy";
function render(){const d=DATA[family],r=d.recommendation,s=d.simulation;
document.querySelector("#growth").textContent=s.growth_cm.toFixed(1)+" см";
document.querySelector("#mechanic").textContent=r.mechanic_first;
document.querySelector("#explanation").textContent=r.mechanic_explanation_user;
document.querySelector("#categories").innerHTML=r.challenge.habitual_items.map(x=>'<span class="tag">'+x.category+'</span>').join("");
document.querySelector("#target").textContent=r.challenge.target_saving_rub;
document.querySelector("#rank").textContent=s.rank;document.querySelector("#members").textContent=s.members;
document.querySelector("#gap").textContent=s.gap_purchase_rub}
document.querySelectorAll("[data-family]").forEach(b=>b.onclick=()=>{family=b.dataset.family;document.querySelectorAll("[data-family]").forEach(x=>x.classList.toggle("active",x===b));render()});
document.querySelectorAll("[data-screen]").forEach(b=>b.onclick=()=>{document.querySelectorAll(".screen").forEach(x=>x.classList.toggle("active",x.id===b.dataset.screen));document.querySelectorAll("[data-screen]").forEach(x=>x.classList.toggle("active",x===b))});render();
</script></body></html>"""


def build(root: Path | str = Path(".")) -> dict[str, object]:
    root = Path(root)
    out_dir = root / "proto"
    out_dir.mkdir(parents=True, exist_ok=True)
    recommendations = {
        row["family_id"]: row
        for row in (
            json.loads(line)
            for line in (root / "ai" / "out" / "challenges.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    simulation = json.loads((root / "sim" / "out" / "summary.json").read_text(encoding="utf-8"))
    data = {
        family_id: {"recommendation": recommendations[family_id], "simulation": simulation["demos"][family_id]}
        for family_id in ["family_ivanovy", "family_dima"]
    }
    (out_dir / "demo.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "index.html").write_text(
        HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False)), encoding="utf-8"
    )
    ivanovy = simulation["demos"]["family_ivanovy"]
    receipt_svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="360" height="560">
<rect width="100%" height="100%" fill="#fff"/><rect x="15" y="15" width="330" height="530" rx="8" fill="#fafafa" stroke="#bbb"/>
<text x="35" y="60" font-family="monospace" font-size="22" font-weight="bold">X5 · РАСТЁМ ВМЕСТЕ</text>
<text x="35" y="105" font-family="monospace" font-size="16">Ростомер Ивановых: +2 см</text>
<text x="35" y="145" font-family="monospace" font-size="16">Всего: {ivanovy['growth_cm']:.1f} см</text>
<text x="35" y="185" font-family="monospace" font-size="16">Веха: привычная корзина</text>
<text x="35" y="225" font-family="monospace" font-size="16">Спасено: 1 продукт</text>
<text x="35" y="265" font-family="monospace" font-size="16">Лига: место {ivanovy['rank']} из {ivanovy['members']}</text>
<line x1="35" y1="305" x2="325" y2="305" stroke="#777" stroke-dasharray="5"/>
<text x="35" y="350" font-family="monospace" font-size="14">Макет цифрового чека.</text>
<text x="35" y="380" font-family="monospace" font-size="14">Кассовая интеграция не реализована.</text>
</svg>"""
    (out_dir / "receipt.svg").write_text(receipt_svg, encoding="utf-8")
    return {"prototype": "proto/index.html", "families": list(data)}
