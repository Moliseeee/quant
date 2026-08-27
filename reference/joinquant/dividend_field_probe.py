# 聚宽 finance.STK_XR_XD 字段探针
# 用法: 聚宽在线 IDE 新建策略，粘贴本文件；区间 2020-01-01 ~ 2020-01-10；运行后贴日志。
# 目的: 一次确认 STK_XR_XD 的真实 DataFrame 列名和样例行，不再猜字段。

from jqdata import *
from jqdata import finance


def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    run_once(probe)
    log.info('DIVIDEND_FIELD_PROBE_INIT_OK')


def probe(context):
    date = context.previous_date
    codes = get_index_stocks('000300.XSHG', date=date)[:20]
    log.info('PROBE_DATE=%s codes=%d' % (date, len(codes)))
    try:
        table = finance.STK_XR_XD
        log.info('STK_XR_XD_DIR=%s' % str([a for a in dir(table) if not a.startswith('_')]))
        q = query(table).filter(table.code.in_(codes))
        df = finance.run_query(q)
        if df is None:
            log.warn('STK_XR_XD_RUN_QUERY_NONE')
            return
        log.info('STK_XR_XD_ROWS=%d' % len(df))
        log.info('STK_XR_XD_COLUMNS=%s' % str(list(df.columns)))
        if len(df) > 0:
            log.info('STK_XR_XD_SAMPLE=%s' % str(df.head(5).to_dict('records'))[:2000])
    except Exception as e:
        log.warn('STK_XR_XD_PROBE_FAILED err=%s' % str(e)[:500])
    log.info('DIVIDEND_FIELD_PROBE_DONE')
