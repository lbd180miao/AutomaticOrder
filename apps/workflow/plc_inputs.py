"""Snapshot-based routing for two alternating racks; input bits are PLC-owned."""
from django.utils import timezone

TRIGGERS = ('position_trigger', 'foam_trigger', 'boxing_trigger',
            'boxing_trigger_2', 'rack_working', 'rack_working_2')


def valid_barcode(value):
    return bool(value) and value.casefold() != 'noread'


def collect_events(observed, samples, *, initialize=False):
    events, messages = [], []
    if initialize:
        for name in TRIGGERS:
            observed[name] = bool(samples[0].get(name))
    for sample in samples:
        now = timezone.now().isoformat()
        for slot, field in ((1, 'rack_barcode'), (2, 'rack_barcode_2')):
            code = str(sample.get(field) or '').strip()
            if valid_barcode(code) and code != observed.get(field):
                observed[field] = code
                observed[field + '_round'] = now + ':' + str(slot)
                events.append({'trigger': 'rack_trigger', 'consumed': True,
                                   'accepted_at': observed[field + '_round'].rsplit(':', 1)[0],
                                   'data': {'rack_barcode': code, 'rack_slot': slot,
                                            'rack_round': observed[field + '_round']}})
                messages.append(('rack', f'料框{slot}码：{code or "空"}'))
        product = str(sample.get('product_barcode') or '').strip()
        if valid_barcode(product) and product != observed.get('product_barcode'):
            observed['product_barcode'] = product
            observed['product_pending'] = True
        simultaneous_work = all(sample.get(name) and observed.get(name) is False
                                for name in ('rack_working', 'rack_working_2'))
        for name in TRIGGERS:
            value = bool(sample.get(name))
            rising = value and observed.get(name) is False
            observed[name] = value
            if not rising:
                continue
            data = {}
            trigger = name
            if name.startswith(('rack_working', 'boxing_trigger')):
                slot = 2 if name.endswith('_2') else 1
                field = 'rack_barcode_2' if slot == 2 else 'rack_barcode'
                data = {'rack_slot': slot, 'rack_barcode': str(sample.get(field) or '').strip(),
                        'rack_round': observed.get(field + '_round')}
                if name.startswith('rack_working'):
                    if simultaneous_work:
                        messages.append(('mes', '[报警] 两个料箱工作信号同时上升，无法唯一确定产品归属；本次不绑定，请复位后重新触发'))
                        continue
                    if not valid_barcode(product) or not valid_barcode(data['rack_barcode']):
                        messages.append(('mes', f'{name}：当前产品码或对应料框码无效，保留有效码记录，等待重触发'))
                        continue
                    if not observed.get('product_pending', False):
                        messages.append(('mes', f'{name}：产品条码未变化且已受理，跳过重复绑定：{product}'))
                        continue
                    data['product_barcode'] = product
                    # Consume at durable queue acceptance, not HTTP completion: a
                    # second edge must not enqueue the same pending/failed upload.
                    observed['product_pending'] = False
                    trigger = 'mark_trigger'
                else:
                    trigger = 'boxing_trigger'
            events.append({'trigger': trigger, 'source_signal': name, 'data': data,
                           'consumed': True, 'accepted_at': timezone.now().isoformat()})
            messages.append(('3d' if name == 'position_trigger' else
                             '2d' if name == 'foam_trigger' else 'mes',
                             f'{name} 0→1，锁定输入：{data}'))
    return events, messages
