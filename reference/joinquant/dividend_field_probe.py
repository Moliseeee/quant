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

    # 1) 首先测试 get_valuation dividend_ratio（JQData SDK 文档明确该字段是股息率）
    try:
        gv = get_valuation(codes, end_date=date, count=1, fields=['dividend_ratio'])
        if gv is None:
            log.warn('GET_VALUATION_DIVIDEND_NONE')
        else:
            log.info('GET_VALUATION_DIVIDEND_ROWS=%d COLUMNS=%s' % (len(gv), str(list(gv.columns))))
            if len(gv) > 0:
                log.info('GET_VALUATION_DIVIDEND_SAMPLE=%s' % str(gv.head(5).to_dict('records'))[:2000])
    except Exception as e:
        log.warn('GET_VALUATION_DIVIDEND_FAILED err=%s' % str(e)[:500])

    # 2) 测 finance 估值表名
    try:
        candidates = [x for x in ['STK_VALUATION', 'STOCK_VALUATION', 'StockValuation'] if hasattr(finance, x)]
        log.info('FINANCE_VALUATION_TABLE_CANDIDATES=%s' % str(candidates))
        for name in candidates:
            table = getattr(finance, name)
            q = query(table).filter(table.code.in_(codes))
            dfv = finance.run_query(q)
            log.info('FINANCE_VALUATION %s rows=%d columns=%s' % (name, 0 if dfv is None else len(dfv), [] if dfv is None else list(dfv.columns)))
            if dfv is not None and len(dfv) > 0:
                log.info('FINANCE_VALUATION_SAMPLE %s %s' % (name, str(dfv.head(3).to_dict('records'))[:1500]))
    except Exception as e:
        log.warn('FINANCE_VALUATION_PROBE_FAILED err=%s' % str(e)[:500])

    # 3) 最后测除权除息明细表
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
            log.info('STK_XR_XD_HINT date_field=a_xr_date cash_field=bonus_ratio_rmb cash_unit=10派X元_divide_by_10')
    except Exception as e:
        log.warn('STK_XR_XD_PROBE_FAILED err=%s' % str(e)[:500])
    log.info('DIVIDEND_FIELD_PROBE_DONE')
