# -*- coding: utf-8 -*-
"""
HTML 대시보드 생성 (단일 파일, 다크 테마, 탭 4개).
외부 의존성은 RRG용 plotly CDN 하나뿐 — 인터넷이 없어도 표(탭1~3)는 보인다.
"""
import os, json
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(HERE, "output")


def _fmt_rs(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return '<span class="na">—</span>'
    cls = "pos" if v > 0 else ("neg" if v < 0 else "flat")
    return f'<span class="{cls}">{v:+.1f}</span>'


def _fmt_pct(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return '<span class="na">—</span>'
    return f"{v:.0f}%"


def _fmt_flow(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return '<span class="na">—</span>'
    cls = "pos" if v >= 1.2 else ("neg" if v < 0.8 else "flat")
    return f'<span class="{cls}">×{v:.2f}</span>'


def _fmt_delta(d):
    if d is None:
        return '<span class="na">·</span>'
    if d > 0:
        return f'<span class="pos">▲{d}</span>'
    if d < 0:
        return f'<span class="neg">▼{abs(d)}</span>'
    return '<span class="flat">—</span>'


def _tag(r):
    if r.get("rotation"):
        return '<span class="badge rot">🔄 로테이션</span>'
    return ""


def _table(rows, scope="theme"):
    head = """<tr>
      <th>#</th><th class="l">이름</th>
      <th>RS5</th><th>RS21</th><th>RS63</th>
      <th>breadth</th><th>거래대금</th>
      <th>전일</th><th>5일전</th><th class="l">태그</th></tr>"""
    body = []
    for r in rows:
        cls = "rot-row" if r.get("rotation") else ""
        etf = f'<span class="etf">{r["etf"]}</span>' if r.get("etf") else ""
        nm = r['name'].replace("'", "")
        body.append(f"""<tr class="{cls}">
          <td class="rk">{r['rank']}</td>
          <td class="l name clk" onclick="gotoRRG('{scope}','{nm}')" title="누르면 로테이션맵에서 보기">{r['name']} <span class="cnt">{r.get('n','')}</span> {etf}</td>
          <td>{_fmt_rs(r['rs5'])}</td>
          <td>{_fmt_rs(r['rs21'])}</td>
          <td>{_fmt_rs(r['rs63'])}</td>
          <td>{_fmt_pct(r['breadth'])}</td>
          <td>{_fmt_flow(r['flow'])}</td>
          <td>{_fmt_delta(r.get('delta1'))}</td>
          <td>{_fmt_delta(r.get('delta5'))}</td>
          <td class="l">{_tag(r)}</td></tr>""")
    return f'<table class="rank"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table>'


def _rrg_payload(rrg):
    """plotly용 데이터(JSON 직렬화)."""
    def pack(items):
        return [{"name": it["name"], "tail": it["tail"], "quadrant": it["quadrant"]} for it in items]
    return {"sectors": pack(rrg.get("sectors", [])),
            "sectors_kr": pack(rrg.get("sectors_kr", [])),
            "themes": pack(rrg.get("themes", []))}


def build(comp_result, rrg, failures):
    date = comp_result["date"]
    bm = comp_result["benchmarks"]
    fail_html = (f'<span class="fail">수집 실패 {len(failures)}: {", ".join(failures)}</span>'
                 if failures else '<span class="ok">수집 실패 없음</span>')
    rrg_json = json.dumps(_rrg_payload(rrg), ensure_ascii=False)

    return f"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>로테이션 랩 · {date}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
:root{{--bg:#0b0d11;--panel:#13161c;--line:#222732;--txt:#e6e8ec;--mut:#8b93a1;
  --pos:#27c498;--neg:#ff5d6c;--flat:#7b8494;--rot:#caa024;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--txt);
  font-family:Pretendard,system-ui,-apple-system,sans-serif;}}
.wrap{{max-width:960px;margin:0 auto;padding:16px;}}
h1{{font-size:19px;margin:2px 0;}}
.meta{{color:var(--mut);font-size:12.5px;margin:6px 0 14px;line-height:1.7;}}
.fail{{color:var(--neg);}} .ok{{color:var(--pos);}}
.tabs{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px;position:sticky;top:0;
  background:var(--bg);padding:8px 0;z-index:5;}}
.tab{{padding:8px 13px;border-radius:9px;background:var(--panel);color:var(--mut);
  font-size:13.5px;font-weight:600;cursor:pointer;border:1px solid var(--line);}}
.tab.on{{color:var(--txt);border-color:#3a4a6a;background:#1a2030;}}
.view{{display:none;}} .view.on{{display:block;}}
table.rank{{width:100%;border-collapse:collapse;font-size:13px;
  font-variant-numeric:tabular-nums;}}
.rank th,.rank td{{padding:8px 6px;text-align:right;border-bottom:1px solid var(--line);
  white-space:nowrap;}}
.rank th{{color:var(--mut);font-weight:600;font-size:11.5px;}}
.rank th.l,.rank td.l{{text-align:left;}}
.rank .rk{{color:var(--mut);font-weight:700;}}
.rank .name{{font-weight:600;}}
.rank td.clk{{cursor:pointer;}}
.rank td.clk:hover{{background:#181d27;text-decoration:underline;text-decoration-color:#3a4a6a;}}
.rank .cnt{{color:var(--mut);font-size:11px;font-weight:400;}}
.rank .etf{{color:#6d7b95;font-size:10.5px;font-weight:600;background:#1a2030;
  border-radius:5px;padding:1px 5px;margin-left:3px;}}
.pos{{color:var(--pos);font-weight:600;}} .neg{{color:var(--neg);font-weight:600;}}
.flat{{color:var(--flat);}} .na{{color:#4a5160;}}
tr.rot-row{{background:rgba(202,160,36,.10);}}
.badge.rot{{background:rgba(202,160,36,.18);color:var(--rot);padding:2px 7px;
  border-radius:6px;font-size:11px;font-weight:700;}}
.note{{color:var(--mut);font-size:12px;margin:6px 0 16px;}}
.rrg-box{{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:8px;margin-bottom:18px;}}
.rrg-box h3{{font-size:14px;margin:6px 8px 0;}}
.sel{{color:#cdd3dd;font-size:13px;margin:6px 8px 8px;padding:8px 11px;
  background:#0e1217;border:1px solid var(--line);border-radius:8px;}}
.btns{{display:flex;flex-wrap:wrap;gap:5px;margin:0 8px 8px;}}
.chip2{{background:#161b23;color:#cdd3dd;border:1px solid #2a3340;border-radius:7px;
  padding:4px 9px;font-size:12px;font-weight:600;cursor:pointer;font-family:inherit;
  border-left-width:3px;}}
.chip2:hover{{background:#1d2530;}}
.chip2.on{{background:#243049;color:#fff;border-color:#4a6aa0;}}
.chip2.all{{border-left-color:#9aa0aa;background:#202632;}}
.chart{{width:100%;height:440px;}}
.legend{{color:var(--mut);font-size:12px;margin:4px 8px 0;}}
.foot{{color:var(--mut);font-size:11.5px;text-align:center;margin:24px 0 8px;}}
</style></head><body><div class="wrap">

<h1>📡 로테이션 랩 <span style="font-size:13px;color:var(--mut);font-weight:500;letter-spacing:1px">ROTATION LAB</span></h1>
<div class="meta">
  기준일 <b>{date}</b> · 벤치마크 미국 {bm['us']} / 한국 {bm['kr']}<br>
  RS = 자산수익률 − 벤치마크수익률 (×100, 거래일 5/21/63) · 종합점수 = 0.5·RS63+0.3·RS21+0.2·RS5<br>
  {fail_html}
</div>

<div class="tabs">
  <div class="tab on" data-v="v1">🔥 테마 랭킹</div>
  <div class="tab" data-v="v2">🇺🇸 섹터(미국)</div>
  <div class="tab" data-v="v3">🇰🇷 섹터(한국)</div>
  <div class="tab" data-v="v4">🌀 로테이션맵</div>
</div>

<div id="v1" class="view on">
  <div class="note">테마 RS = 구성종목 RS의 <b>중앙값</b> · breadth = 52주 신고가 −15% 이내 비율 · 거래대금 = 5일/60일 · 🔄 = RS63 하위50% & RS5 상위20%</div>
  {_table(comp_result['themes'], 'theme')}
</div>
<div id="v2" class="view">{_table(comp_result['us'], 'us')}</div>
<div id="v3" class="view">{_table(comp_result['kr'], 'kr')}</div>

<div id="v4" class="view">
  <div class="note">색: <b style="color:#27c498">주도</b>(우상·강함★) · <b style="color:#508cff">회복</b>(좌상·살아남) · <b style="color:#e0a020">약화</b>(우하·식는중) · <b style="color:#ff5d6c">부진</b>(좌하·약함) · 꼬리=최근 8주 궤적 · <b>점/선을 누르면 그것만 강조+이름표시</b>, 빈곳 더블클릭=전체 · 돈은 시계방향</div>
  <div class="rrg-box"><h3>테마 (기준 {bm['us']})</h3>
    <div id="rrgThemesSel" class="sel">👇 아래 버튼을 누르면 그 선 하나만 떠요</div>
    <div id="rrgThemesBtns" class="btns"></div>
    <div id="rrgThemes" class="chart"></div></div>
  <div class="rrg-box"><h3>섹터 (미국, 기준 {bm['us']})</h3>
    <div id="rrgSectorsSel" class="sel">👇 아래 버튼을 누르면 그 선 하나만 떠요</div>
    <div id="rrgSectorsBtns" class="btns"></div>
    <div id="rrgSectors" class="chart"></div></div>
  <div class="rrg-box"><h3>섹터 (한국, 기준 {bm['kr']})</h3>
    <div id="rrgSectorsKrSel" class="sel">👇 아래 버튼을 누르면 그 선 하나만 떠요</div>
    <div id="rrgSectorsKrBtns" class="btns"></div>
    <div id="rrgSectorsKr" class="chart"></div></div>
</div>

<div class="foot">로테이션 랩 · ROTATION LAB · 자동 생성 {date}</div>
</div>

<script>
const RRG = {rrg_json};
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
  document.querySelectorAll('.view').forEach(x=>x.classList.remove('on'));
  t.classList.add('on');
  document.getElementById(t.dataset.v).classList.add('on');
  if(t.dataset.v==='v4') setTimeout(drawRRG, 30);
}});

const RRGAPI={{}};
let rrgDrawn=false;
function drawRRG(){{
  if(rrgDrawn || typeof Plotly==='undefined') return;
  rrgDrawn=true;
  plotOne('rrgThemes', RRG.themes);
  plotOne('rrgSectors', RRG.sectors);
  plotOne('rrgSectorsKr', RRG.sectors_kr);
}}
// 랭킹표에서 이름 클릭 → 로테이션맵 탭으로 가서 그 선만 강조
function gotoRRG(scope, name){{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
  document.querySelectorAll('.view').forEach(x=>x.classList.remove('on'));
  document.querySelector('.tab[data-v="v4"]').classList.add('on');
  document.getElementById('v4').classList.add('on');
  drawRRG();
  const id = scope==='theme'?'rrgThemes':(scope==='us'?'rrgSectors':'rrgSectorsKr');
  setTimeout(function(){{
    if(RRGAPI[id]) RRGAPI[id].showOnly(name);
    var box=document.getElementById(id); if(box) box.scrollIntoView({{behavior:'smooth',block:'center'}});
  }}, 150);
}}
function plotOne(id, items){{
  if(!items || !items.length){{
    document.getElementById(id).innerHTML='<div style="color:#8b93a1;padding:30px">데이터 부족(구성종목을 채우면 표시됩니다)</div>';
    return;
  }}
  const QC={{'주도':'#27c498','회복':'#508cff','약화':'#e0a020','부진':'#ff5d6c'}};
  const traces=[];
  let xs=[],ys=[];
  // 평소엔 이름표 숨김(겹쳐서 뭉개짐) → 분면별 색으로만 위치 표시. 누르면 이름·수치 뜸.
  items.forEach(it=>{{
    const x=it.tail.map(p=>p.x), y=it.tail.map(p=>p.y);
    xs=xs.concat(x); ys=ys.concat(y);
    const col=QC[it.quadrant]||'#9aa0aa';
    traces.push({{x:x,y:y,mode:'lines+markers',name:it.name,
      line:{{width:1.4,color:col}},
      marker:{{size:x.map((_,i)=>i===x.length-1?12:4),color:col}},
      hovertemplate:it.name+' · 분면 '+it.quadrant+'<br>상대강도 %{{x:.1f}} / 추세 %{{y:.1f}}<extra></extra>'}});
  }});
  const pad=1.2;
  const xmin=Math.min(98,...xs)-pad, xmax=Math.max(102,...xs)+pad;
  const ymin=Math.min(98,...ys)-pad, ymax=Math.max(102,...ys)+pad;
  const layout={{
    paper_bgcolor:'#13161c', plot_bgcolor:'#13161c',
    font:{{color:'#cdd3dd',size:11}}, showlegend:false,
    margin:{{l:48,r:18,t:10,b:40}},
    xaxis:{{title:'상대강도 (오른쪽=강함)',range:[xmin,xmax],zeroline:false,gridcolor:'#222732'}},
    yaxis:{{title:'강도추세 (위=가속)',range:[ymin,ymax],zeroline:false,gridcolor:'#222732'}},
    shapes:[
      {{type:'rect',x0:100,x1:xmax,y0:100,y1:ymax,fillcolor:'rgba(39,196,152,.07)',line:{{width:0}}}},
      {{type:'rect',x0:100,x1:xmax,y0:ymin,y1:100,fillcolor:'rgba(255,93,108,.05)',line:{{width:0}}}},
      {{type:'rect',x0:xmin,x1:100,y0:ymin,y1:100,fillcolor:'rgba(255,93,108,.08)',line:{{width:0}}}},
      {{type:'rect',x0:xmin,x1:100,y0:100,y1:ymax,fillcolor:'rgba(80,140,255,.06)',line:{{width:0}}}},
      {{type:'line',x0:100,x1:100,y0:ymin,y1:ymax,line:{{color:'#3a4150',width:1}}}},
      {{type:'line',x0:xmin,x1:xmax,y0:100,y1:100,line:{{color:'#3a4150',width:1}}}}
    ],
    annotations:[
      {{x:xmax,y:ymax,text:'주도 ★',showarrow:false,font:{{color:'#27c498',size:12}},xanchor:'right',yanchor:'top'}},
      {{x:xmax,y:ymin,text:'약화',showarrow:false,font:{{color:'#ff5d6c',size:12}},xanchor:'right',yanchor:'bottom'}},
      {{x:xmin,y:ymin,text:'부진',showarrow:false,font:{{color:'#ff5d6c',size:12}},xanchor:'left',yanchor:'bottom'}},
      {{x:xmin,y:ymax,text:'회복',showarrow:false,font:{{color:'#508cff',size:12}},xanchor:'left',yanchor:'top'}}
    ]
  }};
  Plotly.newPlot(id,traces,layout,{{displayModeBar:false,responsive:true}});
  const sel=document.getElementById(id+'Sel');
  const gd=document.getElementById(id);
  const btns=document.getElementById(id+'Btns');

  function markBtn(nm){{
    if(!btns) return;
    btns.querySelectorAll('.chip2').forEach(b=>b.classList.toggle('on', b.dataset.nm===nm));
  }}
  // 그 선 '하나만' 표시(나머지는 숨김)
  function showOnly(nm){{
    const it=items.find(o=>o.name===nm); if(!it) return;
    const last=it.tail[it.tail.length-1];
    sel.innerHTML='📍 <b>'+nm+'</b> &nbsp;·&nbsp; 분면 <b style="color:'+(QC[it.quadrant]||'#fff')+'">'+it.quadrant
      +'</b> &nbsp;·&nbsp; 상대강도 '+last.x.toFixed(1)+' / 추세 '+last.y.toFixed(1);
    Plotly.restyle(id,{{visible:items.map(o=>o.name===nm),'line.width':items.map(()=>3),opacity:items.map(()=>1)}});
    markBtn(nm);
  }}
  // 전체 다시 보기
  function showAll(){{
    sel.innerHTML='👇 버튼을 누르면 그 선 하나만 떠요';
    Plotly.restyle(id,{{visible:items.map(()=>true),'line.width':items.map(()=>1.4),opacity:items.map(()=>1)}});
    markBtn(null);
  }}
  RRGAPI[id]={{showOnly:showOnly, showAll:showAll}};
  gd.on('plotly_click',function(ev){{ showOnly(ev.points[0].data.name); }});
  gd.on('plotly_doubleclick',showAll);

  // 이름 버튼 생성(분면 색 테두리) + '전체' 버튼
  if(btns){{
    btns.innerHTML='';
    const all=document.createElement('button');
    all.className='chip2 all'; all.textContent='전체'; all.onclick=showAll;
    btns.appendChild(all);
    items.forEach(it=>{{
      const b=document.createElement('button');
      b.className='chip2'; b.dataset.nm=it.name; b.textContent=it.name;
      b.style.borderLeftColor=(QC[it.quadrant]||'#9aa0aa');
      b.onclick=function(){{ showOnly(it.name); }};
      btns.appendChild(b);
    }});
  }}
}}
</script>
</body></html>"""


def write(comp_result, rrg, failures):
    os.makedirs(OUTPUT, exist_ok=True)
    html = build(comp_result, rrg, failures)
    path = os.path.join(OUTPUT, "dashboard.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
