import os
import json
from datetime import datetime, timezone, timedelta
import gspread
from google.oauth2.service_account import Credentials

GOOGLE_CREDENTIALS = os.environ["GOOGLE_CREDENTIALS"]
GOOGLE_SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
BA_TZ = timezone(timedelta(hours=-3))

TIPOS = ['Desayuno', 'Almuerzo', 'Merienda', 'Cena']

def get_tipo(nombre):
    n = nombre.lower()
    for t in TIPOS:
        if t.lower() in n:
            return t
    return None

def get_sheet_data():
    creds_dict = json.loads(GOOGLE_CREDENTIALS)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1
    return sheet.get_all_records()

def process_data(records):
    data = {}
    for r in records:
        fecha = str(r.get('Fecha', ''))
        comida_raw = str(r.get('Comida', ''))
        tomo = str(r.get('Tomó agua', ''))
        tipo = get_tipo(comida_raw)
        if tipo is None:
            continue
        if fecha not in data:
            data[fecha] = {}
        val = 'si' if 'Sí' in tomo or ('si' in tomo.lower() and 'no' not in tomo.lower()) else 'no'
        if tipo not in data[fecha] or val == 'si':
            data[fecha][tipo] = val
    return data

def get_day_pct(day_data):
    if not day_data:
        return 0
    si = sum(1 for t in TIPOS if day_data.get(t) == 'si')
    return round(si / len(TIPOS) * 100)

def get_color(pct):
    if pct >= 75: return '#5eead4'
    if pct >= 50: return '#a78bfa'
    if pct >= 25: return '#fcd34d'
    return '#fca5a5'

def generate_html(data):
    today = datetime.now(BA_TZ)
    today_key = today.strftime('%d/%m/%Y')
    updated_at = today.strftime('%d/%m/%Y %H:%M')

    print(f"Today key: {today_key}")
    print(f"Datos: {data}")

    all_dates = sorted(data.keys(), key=lambda d: datetime.strptime(d, '%d/%m/%Y') if d else datetime.min)
    last_30 = all_dates[-30:] if len(all_dates) >= 30 else all_dates

    today_data = data.get(today_key, {})
    today_pct = get_day_pct(today_data)
    today_si = sum(1 for t in TIPOS if today_data.get(t) == 'si')
    today_ml = today_si * 500
    bottle_color = get_color(today_pct)

    week_dates = [(today - timedelta(days=i)).strftime('%d/%m/%Y') for i in range(6, -1, -1)]
    week_pcts = [get_day_pct(data.get(d, {})) for d in week_dates]
    week_avg = round(sum(week_pcts) / len(week_pcts)) if week_pcts else 0

    month_pcts = [get_day_pct(data.get(d, {})) for d in last_30]
    month_avg = round(sum(month_pcts) / len(month_pcts)) if month_pcts else 0

    streak = 0
    for i in range(30):
        d = (today - timedelta(days=i)).strftime('%d/%m/%Y')
        if get_day_pct(data.get(d, {})) >= 75:
            streak += 1
        else:
            break

    dias_labels = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb']

    def week_bars():
        html = ''
        for i, d in enumerate(week_dates):
            p = week_pcts[i]
            h = round(p * 0.72)
            is_today = d == today_key
            col = get_color(p)
            dow = datetime.strptime(d, '%d/%m/%Y').weekday()
            label = dias_labels[(dow + 1) % 7]
            lc = '#a78bfa' if is_today else 'rgba(255,255,255,0.45)'
            html += f'<div class="day-col"><div class="day-name" style="color:{lc}">{label}</div><div class="day-bar-wrap"><div class="day-bar" style="height:{h}%;background:{col}"></div></div><div class="day-pct">{p}%</div></div>'
        return html

    def comida_rows(day_d):
        html = ''
        for t in TIPOS:
            val = day_d.get(t)
            if val == 'si': col, icon = '#5eead4', '✓'
            elif val == 'no': col, icon = '#fca5a5', '✗'
            else: col, icon = 'rgba(255,255,255,0.2)', '–'
            bw = 100 if val == 'si' else 0
            html += f'<div class="comida-row"><div class="comida-name">{t}</div><div class="comida-bar-bg"><div class="comida-bar" style="width:{bw}%;background:{col}"></div></div><span style="font-size:14px;color:{col}">{icon}</span></div>'
        return html

    def month_dots():
        html = ''
        for d in last_30:
            p = get_day_pct(data.get(d, {}))
            col = get_color(p)
            op = round(0.25 + p/100*0.75, 2)
            html += f'<div class="month-dot" style="background:{col};opacity:{op}" title="{d}: {p}%"></div>'
        return html

    def comida_month():
        html = ''
        for t in TIPOS:
            si = sum(1 for d in last_30 if data.get(d, {}).get(t) == 'si')
            pct = round(si / len(last_30) * 100) if last_30 else 0
            col = get_color(pct)
            html += f'<div class="comida-row"><div class="comida-name">{t}</div><div class="comida-bar-bg"><div class="comida-bar" style="width:{pct}%;background:{col}"></div></div><div class="comida-pct">{pct}%</div></div>'
        return html

    fill_h = round(today_pct / 100 * 142)
    fill_y = 168 - fill_h
    dias_perfectos = sum(1 for d in last_30 if get_day_pct(data.get(d, {})) == 100)
    tend_val = sum(week_pcts[-7:]) / 7 if week_pcts else 0
    tendencia_col = '#5eead4' if tend_val > month_avg else '#fca5a5'
    tendencia = '↑' if tend_val > month_avg else '↓'
    week_avg_col = get_color(week_avg)
    month_avg_col = get_color(month_avg)
    gh_pat = os.environ.get("GH_PAT", "")

    return f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agua Tracker</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:linear-gradient(135deg,#1a0533 0%,#0d1a3a 40%,#0a2a1a 100%);min-height:100vh;display:flex;align-items:flex-start;justify-content:center;padding:2rem 1rem;font-family:system-ui,-apple-system,sans-serif;color:rgba(255,255,255,0.92)}}
.dash{{width:100%;max-width:680px}}
.glass{{background:rgba(255,255,255,0.1);border:0.5px solid rgba(255,255,255,0.2);border-radius:16px}}
.glass-soft{{background:rgba(255,255,255,0.06);border:0.5px solid rgba(255,255,255,0.1);border-radius:12px}}
.metric-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-bottom:14px}}
.metric-card{{padding:14px}}
.metric-card .label{{font-size:10px;color:rgba(255,255,255,0.45);letter-spacing:.06em;text-transform:uppercase;margin-bottom:5px}}
.metric-card .value{{font-size:24px;font-weight:500}}
.metric-card .sub{{font-size:10px;color:rgba(255,255,255,0.6);margin-top:3px}}
.row{{display:grid;grid-template-columns:190px 1fr;gap:12px;margin-bottom:12px;align-items:start}}
.bottle-wrap{{display:flex;flex-direction:column;align-items:center;gap:8px;padding:16px 12px}}
.pct-label{{font-size:26px;font-weight:500}}
.pct-sub{{font-size:10px;color:rgba(255,255,255,0.45)}}
.panel-pad{{padding:14px}}
.section-title{{font-size:12px;font-weight:500;color:rgba(255,255,255,0.65);margin:0 0 10px}}
.week-grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:5px}}
.day-col{{display:flex;flex-direction:column;align-items:center;gap:4px}}
.day-name{{font-size:10px;color:rgba(255,255,255,0.45)}}
.day-bar-wrap{{height:72px;width:22px;background:rgba(255,255,255,0.06);border-radius:6px;display:flex;align-items:flex-end;overflow:hidden;border:0.5px solid rgba(255,255,255,0.08)}}
.day-bar{{width:100%;border-radius:6px}}
.day-pct{{font-size:10px;color:rgba(255,255,255,0.45)}}
.comida-row{{display:flex;align-items:center;gap:8px;margin-bottom:9px}}
.comida-name{{font-size:12px;color:rgba(255,255,255,0.65);width:68px}}
.comida-bar-bg{{flex:1;height:5px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden}}
.comida-bar{{height:100%;border-radius:3px}}
.comida-pct{{font-size:10px;color:rgba(255,255,255,0.45);width:30px;text-align:right}}
.tabs{{display:flex;gap:5px}}
.tab{{font-size:11px;padding:5px 14px;border-radius:20px;border:0.5px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.45);cursor:pointer;font-family:inherit}}
.tab.active{{background:rgba(167,139,250,0.25);border-color:rgba(167,139,250,0.5);color:#a78bfa}}
.month-grid{{display:grid;grid-template-columns:repeat(10,1fr);gap:4px;margin-bottom:10px}}
.month-dot{{width:100%;aspect-ratio:1;border-radius:3px}}
.legend-row{{display:flex;gap:10px;font-size:10px;color:rgba(255,255,255,0.45);margin-bottom:12px;flex-wrap:wrap}}
.leg-dot{{width:7px;height:7px;border-radius:2px;display:inline-block;margin-right:3px;vertical-align:middle}}
.view{{display:none}}.view.active{{display:block}}
.updated{{font-size:10px;color:rgba(255,255,255,0.3);margin-top:12px;text-align:right}}
.refresh-btn{{font-size:11px;padding:6px 16px;border-radius:20px;border:0.5px solid rgba(167,139,250,0.4);background:rgba(167,139,250,0.15);color:#a78bfa;cursor:pointer;font-family:inherit;margin-left:8px}}
.refresh-btn:disabled{{opacity:0.5;cursor:not-allowed}}
</style>
</head>
<body>
<div class="dash">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">
    <div>
      <div style="font-size:15px;font-weight:500">Hidratación</div>
      <div style="font-size:10px;color:rgba(255,255,255,0.45)">{today.strftime('%A %d de %B').lower()}</div>
    </div>
    <div style="display:flex;align-items:center;gap:8px">
      <div class="tabs">
        <button class="tab active" onclick="showView('dia',this)">Hoy</button>
        <button class="tab" onclick="showView('semana',this)">Semana</button>
        <button class="tab" onclick="showView('mes',this)">Mes</button>
      </div>
      <button class="refresh-btn" onclick="triggerRefresh(this)">↻ Actualizar</button>
    </div>
  </div>

  <div id="view-dia" class="view active">
    <div class="metric-grid">
      <div class="metric-card glass-soft"><div class="label">Hoy</div><div class="value" style="color:{bottle_color}">{today_pct}%</div><div class="sub">{today_ml} ml</div></div>
      <div class="metric-card glass-soft"><div class="label">Racha</div><div class="value" style="color:#a78bfa">{streak}</div><div class="sub">{'días seguidos' if streak > 0 else 'sin racha'}</div></div>
      <div class="metric-card glass-soft"><div class="label">Promedio mes</div><div class="value" style="color:{month_avg_col}">{month_avg}%</div><div class="sub">30 días</div></div>
    </div>
    <div class="row">
      <div class="glass bottle-wrap">
        <div class="pct-label" style="color:{bottle_color}">{today_pct}%</div>
        <svg width="80" height="180" viewBox="0 0 80 180">
          <defs>
            <clipPath id="bc"><rect x="10" y="26" width="60" height="142" rx="14"/></clipPath>
            <linearGradient id="fg" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stop-color="#a78bfa" stop-opacity="0.85"/>
              <stop offset="50%" stop-color="#5eead4" stop-opacity="0.85"/>
              <stop offset="100%" stop-color="#f0abfc" stop-opacity="0.85"/>
            </linearGradient>
            <linearGradient id="bg" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stop-color="rgba(167,139,250,0.18)"/>
              <stop offset="50%" stop-color="rgba(255,255,255,0.28)"/>
              <stop offset="100%" stop-color="rgba(94,234,212,0.12)"/>
            </linearGradient>
          </defs>
          <rect x="26" y="6" width="28" height="22" rx="6" fill="rgba(167,139,250,0.25)" stroke="rgba(167,139,250,0.4)" stroke-width="1"/>
          <rect x="10" y="26" width="60" height="142" rx="14" fill="url(#bg)" stroke="rgba(255,255,255,0.2)" stroke-width="1"/>
          <rect x="10" y="{fill_y}" width="60" height="{fill_h}" fill="url(#fg)" clip-path="url(#bc)"/>
          <rect x="18" y="34" width="5" height="90" rx="2.5" fill="rgba(255,255,255,0.1)"/>
          <text x="40" y="100" text-anchor="middle" font-size="12" font-weight="500" fill="rgba(255,255,255,0.85)">{today_ml} ml</text>
        </svg>
        <div class="pct-sub">{today_si} / {len(TIPOS)} comidas</div>
      </div>
      <div class="glass panel-pad">
        <div class="section-title">Desglose por comida</div>
        {comida_rows(today_data)}
      </div>
    </div>
    <div class="glass panel-pad">
      <div class="section-title">Esta semana</div>
      <div class="week-grid">{week_bars()}</div>
    </div>
  </div>

  <div id="view-semana" class="view">
    <div class="metric-grid">
      <div class="metric-card glass-soft"><div class="label">Promedio semana</div><div class="value" style="color:{week_avg_col}">{week_avg}%</div><div class="sub">esta semana</div></div>
      <div class="metric-card glass-soft"><div class="label">Racha</div><div class="value" style="color:#a78bfa">{streak}</div><div class="sub">días seguidos</div></div>
      <div class="metric-card glass-soft"><div class="label">Promedio mes</div><div class="value" style="color:{month_avg_col}">{month_avg}%</div><div class="sub">30 días</div></div>
    </div>
    <div class="glass panel-pad" style="margin-bottom:12px">
      <div class="section-title">Rendimiento esta semana</div>
      <div class="week-grid" style="margin-bottom:14px">{week_bars()}</div>
      <div class="section-title">Por comida esta semana</div>
      {comida_rows(today_data)}
    </div>
  </div>

  <div id="view-mes" class="view">
    <div class="metric-grid">
      <div class="metric-card glass-soft"><div class="label">Promedio mes</div><div class="value" style="color:{month_avg_col}">{month_avg}%</div><div class="sub">30 días</div></div>
      <div class="metric-card glass-soft"><div class="label">Días perfectos</div><div class="value" style="color:#5eead4">{dias_perfectos}</div><div class="sub">100% del día</div></div>
      <div class="metric-card glass-soft"><div class="label">Racha</div><div class="value" style="color:#a78bfa">{streak}</div><div class="sub">días seguidos</div></div>
      <div class="metric-card glass-soft"><div class="label">Tendencia</div><div class="value" style="color:{tendencia_col}">{tendencia}</div><div class="sub">vs promedio</div></div>
    </div>
    <div class="glass panel-pad">
      <div class="section-title">Últimos 30 días</div>
      <div class="month-grid">{month_dots()}</div>
      <div class="legend-row">
        <span><span class="leg-dot" style="background:#5eead4"></span>75–100%</span>
        <span><span class="leg-dot" style="background:#a78bfa"></span>50–74%</span>
        <span><span class="leg-dot" style="background:#fcd34d"></span>25–49%</span>
        <span><span class="leg-dot" style="background:#fca5a5"></span>0–24%</span>
      </div>
      <div class="section-title">Por comida este mes</div>
      {comida_month()}
    </div>
  </div>

  <div class="updated">Actualizado: {updated_at}</div>
</div>
<script>
function showView(view, btn) {{
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('view-' + view).classList.add('active');
  btn.classList.add('active');
}}
function triggerRefresh(btn) {{
  btn.disabled = true;
  btn.textContent = '↻ Actualizando...';
  fetch('https://api.github.com/repos/MicaelaGonzalezEscudero/agua-dashboard/actions/workflows/generate_dashboard.yml/dispatches', {{
    method: 'POST',
    headers: {{'Authorization': 'token {gh_pat}', 'Content-Type': 'application/json'}},
    body: JSON.stringify({{ref: 'main'}})
  }}).then(r => {{
    if (r.status === 204) {{
      btn.textContent = '✓ Generando...';
      setTimeout(() => window.location.reload(), 25000);
    }} else {{
      btn.textContent = '↻ Actualizar';
      btn.disabled = false;
    }}
  }}).catch(() => {{ btn.textContent = '↻ Actualizar'; btn.disabled = false; }});
}}
</script>
</body>
</html>'''

if __name__ == "__main__":
    print("Leyendo datos de Google Sheets...")
    records = get_sheet_data()
    print(f"Registros encontrados: {len(records)}")
    data = process_data(records)
    print(f"Días con datos: {len(data)}")
    html = generate_html(data)
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("Dashboard generado!")
