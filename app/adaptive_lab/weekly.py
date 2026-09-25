"""Frozen weekly Lab product reporting; no provider or model-training dependency."""
from __future__ import annotations
import asyncio
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from .contracts import digest,utc
from app.lab_combo.publication_window import RIGA,local
from app.real_match_lab_analysis.models import LAB_CHAT_ID

REPORT_VERSION='LAB_WEEKLY_V1'


def week_bounds(now: datetime) -> tuple[datetime,datetime]:
    """Local calendar arithmetic preserves Monday midnight across DST changes."""
    clock=local(now);start=(clock-timedelta(days=clock.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
    return start,start+timedelta(days=7)


def latest_due(now: datetime) -> datetime:
    start,_=week_bounds(now);due=start+timedelta(days=6,hours=22,minutes=30)
    return due if local(now)>=due else due-timedelta(days=7)


def next_scheduled(now: datetime) -> datetime:
    due=latest_due(now)
    return due+timedelta(days=7)


def statistics(ledger: object, *, week_start: datetime, as_of: datetime) -> dict:
    """Publication-week cohorts, with immutable results available by the as-of clock."""
    start,end=week_bounds(week_start)
    if local(week_start)!=start:raise ValueError('MONDAY_MIDNIGHT_REQUIRED')
    cutoff=min(utc(end),utc(as_of));diagnostics=[];output={}
    for product,kind,result_kind,prefixes in (
        ('SINGLE','single_prediction','single_settlement',('single_prediction:',)),
        ('COMBO','prediction','settlement',('combo_prediction:','prediction:'))):
        selected=[]
        for p in ledger.all(kind):
            if p.get('stream') in {'LIVE','OFFICIAL'} or p.get('product') in {'LIVE','OFFICIAL'}:continue
            identity=p['prediction_id']
            receipts=[ledger.get('receipt',prefix+identity) for prefix in prefixes]
            receipts=[r for r in receipts if r and r.get('sent') is True and r.get('status')=='SENT'
                      and str(r.get('chat_id'))==str(LAB_CHAT_ID)
                      and type(r.get('message_id')) is int and r['message_id']>0]
            if not receipts:continue
            if len(receipts)!=1 or not receipts[0].get('sent_at_utc'):
                diagnostics.append({'identity':identity,'reason':'PUBLICATION_WEEK_UNPROVEN'});continue
            published=utc(local(receipts[0]['sent_at_utc']))
            if not utc(start)<=published<utc(end) or published>cutoff:continue
            settled=ledger.get(result_kind,identity)
            if settled and (not settled.get('settled_at_utc') or utc(settled['settled_at_utc'])>utc(as_of)):
                settled=None
            selected.append((p,settled))
        counts={k:0 for k in ('WON','LOST','VOID','PARTIAL_VOID')};pnl=Decimal(0);odds=[];pending=0;partial_count=0
        for p,s in selected:
            if s is None:pending+=1;continue
            status=s['status']
            if status not in counts:raise ValueError('INVALID_LAB_SETTLEMENT_STATUS')
            captured=Decimal(str(p['captured_odds'] if product=='SINGLE' else p['combined_odds']))
            if not captured.is_finite() or captured<=1:raise ValueError('INVALID_CAPTURED_ODDS')
            units=Decimal(str(s['unit_result']))
            if not units.is_finite():raise ValueError('INVALID_SETTLEMENT_PNL')
            odds.append(captured);counts[status]+=1;pnl+=units
            if product=='COMBO' and (s.get('partial_void') or status=='PARTIAL_VOID'):partial_count+=1
        settled_count=len(selected)-pending;binary=counts['WON']+counts['LOST']+counts['PARTIAL_VOID']
        output[product]={'published':len(selected),'settled':settled_count,**counts,'pending':pending,
          'hit_rate':str(Decimal(counts['WON']+counts['PARTIAL_VOID'])/binary) if binary else None,
          'flat_unit_pnl':str(pnl),'flat_unit_roi':str(pnl/settled_count) if settled_count else None,
          'average_odds':str(sum(odds)/len(odds)) if odds else None}
        if product=='COMBO':output[product]['partial_void_count']=partial_count
    from app.lab_v2_shadow.statistics import single_cohorts
    cohorts = single_cohorts(ledger, start=start, end=end, as_of=as_of)
    return {'week_start':start.isoformat(),'week_end':end.isoformat(),'as_of':utc(as_of).isoformat(),
            'v2_single_cohorts': cohorts,
            'timezone':'Europe/Riga',**output,'diagnostics':diagnostics,'LIVE':'EXCLUDED','Official':'EXCLUDED'}


def message(report: dict) -> str:
    stats=report['statistics'];start=local(stats['week_start']);end=local(stats['as_of'])
    lines=['📊 GOALVISION AI — WEEKLY RESULTS',f'📅 {start:%d.%m.%Y}–{end:%d.%m.%Y} ({end:%H:%M} Europe/Riga)']
    for name,icon in (('SINGLE','⚽'),('COMBO','🧩')):
        s=stats[name]
        percent=lambda value:'N/A' if value is None else f'{Decimal(value)*100:.1f}%'
        avg='N/A' if s['average_odds'] is None else f"{Decimal(s['average_odds']):.2f}"
        lines.extend(['',f'{icon} {name}',f"Published: {s['published']} · Settled: {s['settled']}",
          f"✅ Won: {s['WON']} · ❌ Lost: {s['LOST']} · ↩️ Void: {s['VOID']}",
          f"Pending: {s['pending']}",f"🎯 Hit rate: {percent(s['hit_rate'])}",
          f"💰 Flat P/L: {Decimal(s['flat_unit_pnl']):+.2f}u · ROI: {percent(s['flat_unit_roi'])}",f'Average odds: {avg}'])
        if name=='COMBO':lines.append(f"Partial void: {s['partial_void_count']} (partial-void wins: {s['PARTIAL_VOID']})")
    cohorts = stats.get('v2_single_cohorts', {})
    forward = cohorts.get('forward_union')
    if forward and forward['published']:
        lines.extend(['', '🧪 V2 atlase · jaunais SINGLE segments',
            f"Published: {forward['published']} · Pending: {forward['pending']} · W/L/VOID: {forward['WON']}/{forward['LOST']}/{forward['VOID']}",
            f"Hypothetical P/L: {forward['flat_unit_pnl']}u · ROI: {percent(forward['flat_unit_roi'])} · n={forward['sample_size']}",
            f"Selector exclusive: {cohorts['selector_exclusive']['published']} · Multiple-origin overlap: {cohorts['multi_origin_overlap']['published']}",
            f"Linked context (observation): {cohorts['context_linked_observation_only']['published']} · ROI denominator: {forward['roi_denominator_units']} settled units (includes VOID).",
            'Football Context V2: observation only; independent model publications: 0.',
            'Overlapping cohorts are subsets of this total; never add them.'])
    lines.extend(['','Hypothetical signals, not realized cash profit.',
                  'Flat units; settled bets only in ROI. Full voids excluded from hit rate.',
                  'Combo hit rate includes partial-void wins.'])
    return '\n'.join(lines)


def freeze(repository: object, ledger: object, *, now: datetime) -> dict:
    """Latest due Sunday; Persistent catch-up never shifts the report cutoff."""
    end=latest_due(now);start,_=week_bounds(end)
    key={'product':'LAB_SINGLE_AND_COMBO','week_start':start.isoformat(),'week_end':end.isoformat(),
         'timezone':'Europe/Riga','report_version':REPORT_VERSION}
    identity='weekly-'+digest(key)
    with repository.transaction():
        existing=repository.get('weekly_reports',identity)
        if existing:return existing
        value={**key,'report_id':identity,'statistics':statistics(ledger,week_start=start,as_of=end)}
        value['message']=message(value)
        repository.append('weekly_reports',identity,'PREMATCH',value,utc(now).isoformat())
        return value


async def deliver(repository: object, report: dict, config: object, transport: object, *, now: datetime) -> dict:
    """Durable at-most-once send attempt; ambiguous outcomes require reconciliation."""
    from app.lab_telegram.service import validate_lab_telegram_config
    identity=report['report_id'];stamp=utc(now).isoformat()
    if validate_lab_telegram_config(config) is not None:return {'status':'LAB_CONFIGURATION_REJECTED','sent':False}
    if repository.get('weekly_reports',identity)!=report:raise ValueError('WEEKLY_REPORT_NOT_FROZEN')
    if len(report['message'])>4096:raise ValueError('TELEGRAM_MESSAGE_TOO_LONG')
    with repository.transaction():
        receipt=repository.get('weekly_receipts',identity)
        if receipt:return {'status':'ALREADY_SENT','sent':False}
        if repository.get('weekly_claims',identity):return {'status':'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED','sent':False}
        repository.append('weekly_claims',identity,'PREMATCH',{'report_id':identity,'message_fingerprint':digest(report['message']),
             'chat_id':LAB_CHAT_ID},stamp,report_id=identity)
    try:
        receipt=await asyncio.wait_for(transport.send_message_receipt(chat_id=LAB_CHAT_ID,text=report['message'],
                                            parse_mode=None,timeout_seconds=10),timeout=11)
        if receipt.chat_id!=LAB_CHAT_ID or type(receipt.message_id) is not int or receipt.message_id<=0:
            raise ValueError('INVALID_RECEIPT')
    except Exception:
        repository.append('weekly_delivery_unknown',identity,'PREMATCH',{'report_id':identity,'status':'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED'},stamp,claim_id=identity)
        return {'status':'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED','sent':False}
    repository.append('weekly_receipts',identity,'PREMATCH',{'report_id':identity,'status':'SENT','sent':True,
                'chat_id':receipt.chat_id,'message_id':receipt.message_id,'sent_at_utc':stamp},stamp,claim_id=identity)
    return {'status':'SENT','sent':True}
