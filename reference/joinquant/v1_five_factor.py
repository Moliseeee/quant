# v1 五因子选股组合 — 聚宽复现版（Codex 修复版 v3）
# 来源: github.com/Moliseeee/quant v1.0.0
# 策略: 低换手0.40 / 低PB0.20 / 高股息0.15 / E-P0.10 / 低PS0.10
# 调仓: 每周最后交易日收盘后，Top8，行业≤3，等权
# 回测建议: 2020-01-01 ~ 2026-08-23，基准 000300.XSHG，初始资金 20 万
#
# 修复记录 2026-08-26（Codex 排查）:
#   1. market_cap 单位=亿元！>5e9 是"50亿亿元"→股票池恒空。改为 >50（50亿元）
#   2. run_weekly weekday 语义=每周第N个交易日(1~5)，-1=最后交易日；time 用 'close'
#      （日频回测不触发 14:30 盘中时点！'close' 日频/分钟都触发）
#   3. get_fundamentals 显式 date=previous_date（避免未来数据限制）
#   4. 高股息用因子库 divyild（end_date=previous_date, count=1）
#   5. 等权目标=portfolio.total_value/N（不是 available_cash）
#   6. get_industry 取 jq_l1 层级；失败返回 UNKNOWN_<code>（不共用桶）

def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    set_order_cost(OrderCost(open_tax=0, close_tax=0.0005,
                             open_commission=0.00025, close_commission=0.00025,
                             close_today_commission=0, min_commission=5), type='stock')
    set_slippage(FixedSlippage(0.02))

    g.N = 8
    g.MAX_PER_INDUSTRY = 3
    g.week_count = 0

    # 每周最后交易日收盘后调仓（-1=最后交易日；'close' 日频/分钟回测均触发）
    run_weekly(rebalance, weekday=-1, time='close')
    # 调度探针: 确认定时任务真的触发
    run_daily(schedule_probe, time='14:29')
    log.info('INIT_OK')


def schedule_probe(context):
    log.info('DAILY_PROBE ' + str(context.current_dt)[:19])


def rebalance(context):
    g.week_count += 1
    log.info('REBALANCE_CALLED week=%d date=%s' % (g.week_count, str(context.current_dt)[:19]))
    rebalance_impl(context)


def rebalance_impl(context):
    data_date = context.previous_date
    # 1. 股票池（market_cap 单位=亿元！>50 即 50亿元）
    q = query(valuation.code,
              valuation.pe_ratio, valuation.pb_ratio, valuation.ps_ratio,
              valuation.turnover_ratio, valuation.market_cap
              ).filter(
        valuation.pe_ratio > 0,
        valuation.pb_ratio > 0,
        valuation.ps_ratio > 0,
        valuation.turnover_ratio > 0,
        valuation.market_cap > 50
    )
    raw = get_fundamentals(q, date=data_date)
    log.info('REBALANCE_POOL date=%s rows=%d' % (data_date, len(raw)))
    if len(raw) < 30:
        log.warn('POOL_TOO_SMALL rows=%d' % len(raw))
        return
    df = raw.dropna(subset=['pe_ratio', 'pb_ratio', 'ps_ratio', 'turnover_ratio',
                            'market_cap']).set_index('code')

    # 2. 高股息: 聚宽因子库 divyild（barra 股息率）
    df['divyild'] = 0.0
    try:
        from jqfactor import get_factor_values
        fv = get_factor_values(securities=list(df.index), factors=['divyild'],
                               end_date=data_date, count=1)
        if fv and 'divyild' in fv and len(fv['divyild']) > 0:
            df['divyild'] = fv['divyild'].iloc[-1].reindex(df.index).fillna(0.0)
            log.info('REBALANCE_DIVYILD ok, 非零=%d' % int((df['divyild'] > 0).sum()))
        else:
            log.warn('REBALANCE_DIVYILD 空结果')
    except Exception as e:
        log.warn('divyild 失败(高股息退化中性): %s' % str(e)[:100])

    # 3. 方向标准化打分（截面百分位 0~1）
    def pct(s, reverse=False):
        r = s.rank(pct=True)
        return 1 - r if reverse else r

    score = (0.40 * pct(df['turnover_ratio'], reverse=True)
             + 0.20 * pct(df['pb_ratio'], reverse=True)
             + 0.15 * pct(df['divyild'])
             + 0.10 * pct(1.0 / df['pe_ratio'])
             + 0.10 * pct(df['ps_ratio'], reverse=True))
    df['score'] = score
    df = df.sort_values('score', ascending=False)

    # 4. TopN + 行业≤3（贪心）
    picked = []
    ind_count = {}
    for code in df.index:
        if len(picked) >= g.N:
            break
        ind_name = get_industry_name(code, data_date)
        if ind_count.get(ind_name, 0) >= g.MAX_PER_INDUSTRY:
            continue
        ind_count[ind_name] = ind_count.get(ind_name, 0) + 1
        picked.append(code)
    if not picked:
        log.warn('NO_PICKED')
        return
    log.info('REBALANCE_PICKED n=%d %s' % (len(picked), picked))

    # 5. 可交易过滤（停牌/ST）
    current_data = get_current_data()
    tradable = [c for c in picked
                if not current_data[c].paused and not current_data[c].is_st]
    log.info('REBALANCE_TRADABLE n=%d %s' % (len(tradable), tradable))
    if not tradable:
        log.warn('NO_TRADABLE')
        return

    # 6. 等权调仓（目标=总资产/N，先卖后买）
    for code in set(context.portfolio.positions.keys()) - set(tradable):
        order_target_value(code, 0)
    target_value = context.portfolio.total_value / len(tradable)
    for code in tradable:
        order = order_target_value(code, target_value)
        log.info('ORDER code=%s target=%.0f result=%s' % (code, target_value, str(order)))


def get_industry_name(code, date):
    """聚宽行业归属（jq_l1 层级；失败返回 UNKNOWN_<code> 不共用桶）"""
    try:
        info = get_industry(code, date=date).get(code, {})
        jq_l1 = info.get('jq_l1')
        if jq_l1:
            return jq_l1.get('industry_name', 'UNKNOWN_' + code)
    except Exception as e:
        log.warn('INDUSTRY_FAILED code=%s err=%s' % (code, str(e)[:120]))
    return 'UNKNOWN_' + code
