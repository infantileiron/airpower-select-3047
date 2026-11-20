import {state} from '../stores/session.js';import {esc} from '../utils/html.js';import {table} from '../components/common/table.js';import {field} from '../components/common/fields.js';import {badge} from '../components/common/status.js';import {HOUR_SOURCES} from '../constants/enums.js';
export function render(){
 const rec=state.selectedRecon;const active=rec?.active;const result=active?.result;
 return `<div class="split"><section class="panel">
 <h2>日电量对账与缺测补值</h2>
 <p class="notice">录入独立日总量与缺测小时上限后补算缺口：各小时之和精确等于日总量，实测小时不修改；补值标记 filled，始终不进入训练。迟到实测入库后旧对账自动失效。</p>
 <h3>对账日列表</h3>
 ${state.recons.length?table(['日期','日总量','状态','活跃版本','版本数'],state.recons.map(r=>[r.day,r.daily_total,r.status,r.active?('v'+r.active.version_no+' · '+r.active.state):'—',r.versions.length])):'<p>暂无对账记录。在右侧录入首个对账日。</p>'}
 ${state.recons.map(r=>`<button class="study" data-recon="${r.id}">#${r.id} ${esc(r.day)} · ${esc(r.status)} ${r.active?'v'+r.active.version_no:''}</button>`).join('')}
 ${rec?renderDetail(rec,active,result):''}
 </section><aside class="side">
 <h2>${rec?'重算 / 调整':'新建对账补录'}</h2>
 <form id="recon">
 ${field('对账日期（本地）','day','date',`required value="${rec?esc(rec.day):''}"`)}
 ${field('独立日总量 / kWh','daily_total','number',`required min=0 step=0.001 value="${rec?esc(rec.daily_total):''}"`)}
 <label>缺测小时上限（每行：YYYY-MM-DDTHH:00=上限，可多行）<textarea name="upper_limits" rows="4" placeholder="2026-11-01T03:00=120&#10;2026-11-01T04:00=120" required>${rec?esc(Object.entries(rec.upper_limits).map(([h,c])=>h+'='+c).join('\n')):''}</textarea></label>
 <p>已有实测的小时不能再给上限；上限之和须不小于缺口。</p>
 <button class="primary">${rec?'基于该日重算（生成新版本）':'补算并发布'}</button>
 </form>
 ${rec?`<button id="recompute" data-recon-id="${rec.id}">直接重算当前对账日</button> <button id="recon-export" data-recon-id="${rec.id}">导出活跃版本</button>`:''}
 </aside></div>`;
}
function renderDetail(rec,active,result){
 if(!active)return `<h3>#${rec.id} ${esc(rec.day)}</h3><p class="notice">尚无已发布版本。</p>`;
 return `<h3>#${rec.id} ${esc(rec.day)} ${badge(rec.status)} / ${badge(active.state)} v${active.version_no}</h3>
 <div class="metrics">
 <div><strong>${esc(result?.daily_total)}</strong>日总量 / kWh</div>
 <div><strong>${esc(result?.measured_sum)}</strong>实测合计</div>
 <div><strong>${esc(result?.gap)}</strong>缺口 = 补值合计</div>
 <div><strong>${esc(result?.residual)}</strong>配平差额（须为0）</div>
 </div>
 ${result?`<h3>逐小时来源与差额核对</h3>
 ${table(['本地小时','来源','耗电kWh','班次曲线','上限','与左实测落差','与右实测落差'],result.hours.map(h=>[h.hour,HOUR_SOURCES[h.source]||h.source,h.kwh,h.profile??'—',h.upper??'—',h.left_gap??'—',h.right_gap??'—']))}
 <p class="notice">实测小时原样保留；补值小时显示同班次历史均值、上限及与缺口两端实测的落差。</p>
 <h4>版本时间线</h4>
 ${rec.versions.map(v=>`<p>v${v.version_no} · ${esc(v.state)} · ${esc(v.reason||'')} ${v.error?`<span class="error">${esc(v.error)}</span>`:''} <small>${esc(v.created||'')}</small></p>`).join('')}
 <details><summary>方法与口径</summary><p class="notice">${esc(result.method)}</p><p>checksum: ${esc(result.checksum)}</p></details>`:'<p class="notice">'+esc(active.error||'无结果')+'</p>'}`;
}
