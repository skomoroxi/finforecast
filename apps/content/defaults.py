"""English default templates, ported from the small site (src/lib/text.ts, assetContent.ts).

COMMON applies to every class; CLASSES adds or replaces fields for one class. Syntax: templating.py.
These only seed the database: after that the admin owns them.
"""

COMMON = {
    "title": "{name} {Noun} Prediction {year}–{last_year}: Daily Forecast",
    "meta_description": "{title_name} forecast: {price} today, {forecast_30d} in 30 days, monthly to {last_year} and yearly to {last_yearly}, updated daily.",
    "h1": "{name} {Noun} Prediction & Forecast {year}–{last_year} ({code})",
    "h_summary": "{title_name} forecast at a glance",
    "h_chart": "{title_name} price chart and forecast",
    "h_next30": "{name} {noun} prediction for the next 30 days",
    "h_tomorrow": "{code} {noun} prediction for tomorrow and next week",
    "h_this_year": "{name} {noun} prediction {year}",
    "h_five_years": "{title_name} {noun} prediction {next_year}–{last_year} (next 5 years)",
    "h_year": "{name} {noun} prediction {this_year}",
    "h_outlook": "{name} {noun} outlook to {last_yearly} (next 10 years)",
    "h_ta": "{title_name} technical analysis",
    "h_analysts": "What analysts and banks predict for {subject}",
    "h_drivers": "What will drive {subject} prices",
    "h_history": "{title_name} price history (last 5 and 10 years)",
    "h_investment": "Is {subject} a good investment in {year}?",
    "h_accuracy": "How we forecast {subject} and how accurate we are",
    "h_faq": "{name} price prediction FAQ",
    "reviewer": "Margerie Holtz",
    "intro": """Daily {subject} {noun} forecasts for the next 30 days, monthly averages for every month to December {last_year} and a yearly outlook to {last_yearly}, from three independent statistical models.
~~
This page forecasts the {subject} {noun} for the next 30 days, for every month through {last_year} and for each year to {last_yearly}, using three different statistical models and their consensus.

The forecasts, the technical analysis and this text are recalculated automatically every day from the latest closing price.
~~
Everything on this page is recalculated every day after the market close, so the numbers always start from the latest price.""",
    "summary": """{Subject} closed at {price} {unit_label}. The model consensus expects {forecast_30d} in 30 days, {forecast_end_year} at the end of {year} and {forecast_2030} by December {last_year}. Today's daily technical signal is {ta_daily}.
~~
From today's close of {price}, the three models together point to {forecast_30d} in a month, {forecast_end_year} by the end of {year} and {forecast_2030} in December {last_year}. The daily technical summary reads {ta_daily}.""",
    "next30": """Over the next 30 days the consensus expects {subject} to {move_30d}, to about {forecast_30d} on {date_30d}.
~~
By {date_30d}, the average of the three models puts {subject} at {forecast_30d}, so the price would {move_30d} from today.

The 80% range for that day is {low_30d} to {high_30d}: daily moves of a few percent are normal for {subject}, so treat single-day values as a guide to direction rather than exact prices.
~~
There is real uncertainty even a month ahead: 80% of model outcomes for that day fall between {low_30d} and {high_30d}.

The highest consensus value in this window is {peak_30d}.""",
    "year_text": """For {period}, the consensus averages **{year_avg}** {unit_label}, {year_change} versus today. The strongest month is {year_best_month} at {year_best}; the weakest is {year_worst_month} at {year_worst}.
~~
The models expect {subject} to average **{year_avg}** over {period} ({year_change} from today), with monthly averages between {year_worst} in {year_worst_month} and {year_best} in {year_best_month}.

The three methods disagree by design: ARIMA averages {year_arima}, trend + reversion {year_reversion} and Monte Carlo {year_montecarlo}. The 80% range across {period} runs from {year_low} to {year_high}.
~~
By method, the averages for {period} are {year_arima} (ARIMA), {year_reversion} (trend + reversion) and {year_montecarlo} (Monte Carlo); 80% of outcomes fall between {year_low} and {year_high}.

December {this_year} consensus: **{year_december}**.""",
    "outlook": """?has_outlook: Beyond {last_year} the forecast uses only the two long-run models. Their consensus moves from {long_first} in {long_first_year} to {long_last} in {long_last_year}.
~~
For {long_first_year}–{long_last_year} only trend + reversion and Monte Carlo are used; together they average {long_first} in {long_first_year} and {long_last} in {long_last_year}.

The models pull in different directions: trend + reversion expects {reversion_last} by {long_last_year}, Monte Carlo {montecarlo_last}. The 80% band for {long_last_year} is extremely wide, {p10_2035} to {p90_2035}, which is the honest answer to "where will {subject} be in 10 years": nobody knows precisely.

?price_above_trend: Today the price sits {trend_gap} above its long-run trend, so the trend + reversion model expects it to drift back toward that line.

?price_below_trend: Today the price sits {trend_gap} below its long-run trend, so the trend + reversion model expects some recovery toward that line, limited by the growth cap.

?montecarlo_up: Monte Carlo continues the long-run growth rate, capped at 25% a year; it says what happens if the past trend simply carries on, not that it will.""",
    "technical": """Technical indicators read {ta_daily} on the daily chart, {ta_weekly} on the weekly and {ta_monthly} on the monthly.
~~
The technical summary is {ta_daily} for the daily timeframe, {ta_weekly} for weekly and {ta_monthly} for monthly.

The 14-day RSI stands at {rsi}.

The price is {ma200_side} its 200-day moving average ({ma200}).

?close_only: Only closing prices are available here, so indicators that need the daily high and low are not shown.

Technical signals describe the recent trend; they are not a forecast of where the price will be.""",
    "accuracy": """?has_accuracy: On average, {accuracy_basis}, the consensus missed the actual price by {mape_1d}% one day ahead, {mape_7d}% one week ahead and {mape_30d}% 30 days ahead.""",
    "faq": """What is the {subject} price forecast for {year}? :: The model consensus expects {subject} to average {forecast_end_year} {unit_label} in December {year}, {change_end_year} versus the latest close of {price}.

What will the {subject} price be tomorrow? :: For {tomorrow_date}, the consensus is {forecast_tomorrow}, with an 80% range of {tomorrow_low} to {tomorrow_high}. Day-to-day moves are mostly noise, so the range matters more than the point value.

What will {subject} be worth next month? :: In 30 days the consensus is {forecast_30d}, a {change_30d} change from the latest close.

How much will {subject} be worth in {last_year}? :: The consensus for December {last_year} is {forecast_2030}. ARIMA follows recent price behaviour, trend + reversion pulls the price toward its long-run trend, and Monte Carlo continues the long-run growth rate (capped at 25% a year).

?goal_central: Will {subject} reach {goal} by {last_year}? :: Yes in the central scenario: the December {last_year} consensus is {forecast_2030}, above {goal}. The 80% range is wide, so this is far from certain.

?goal_possible: Will {subject} reach {goal} by {last_year}? :: It is possible but not the central case: the {last_year} consensus is {forecast_2030}, while the upper end of the 80% range reaches {p90_2030}. Only the more optimistic model paths get to {goal}.

?goal_unlikely: Will {subject} reach {goal} by {last_year}? :: Not in the central scenario: the {last_year} consensus is {forecast_2030} and even the upper end of the 80% range stays at {p90_2030}.

How much will {subject} be worth in 10 years? :: For {long_last_year} the long-run models average {long_last}, but 80% of outcomes fall anywhere between {p10_2035} and {p90_2035}. Ten-year forecasts carry very large uncertainty.

Is {subject} a buy or sell right now? :: The daily technical summary currently reads {ta_daily}. That describes the recent trend only. FinForecast does not give investment advice; consider your own goals and risk before buying or selling.

How accurate are these {subject} predictions? :: On average, {accuracy_basis}, the consensus missed the actual price by {mape_1d}% one day ahead, {mape_7d}% one week ahead and {mape_30d}% 30 days ahead. Errors grow quickly with the horizon.""",
}

CLASSES = {
    "crypto": {
        "drivers": """Market sentiment :: Crypto prices react strongly to the mood of the market, and most coins tend to move together with Bitcoin.

Adoption and use :: Real use of a network, and the number of people and projects building on it, supports demand over time.

Token supply :: How many coins exist, how fast new ones are created and how they are distributed shape the balance of supply and demand.

Regulation :: Rules on exchanges, stablecoins and listed products can open a market or close it, often with little warning.

Interest rates and liquidity :: Crypto tends to do better when money is cheap and investors accept more risk, and worse when conditions tighten.""",
        "bull": """Wider adoption would raise demand for the network and its coin.

New listings and regulated products can bring in investors who could not buy before.

Periods of cheap money have tended to favour risk assets such as crypto.""",
        "bear": """Tighter regulation could limit where the coin can be traded or held.

Competing networks can take users and developers away.

When investors reduce risk, crypto usually falls harder than other assets.""",
        "risks": """Crypto trades around the clock and can move sharply overnight or at weekends.

Holding coins on an exchange carries custody risk; self-custody carries the risk of losing access.

Regulation differs between countries and can change quickly.

The coin produces no income, so returns depend entirely on the price.""",
    },
    "stock": {
        "price_note": """?is_adr: This price is in euros and is close to the XETRA price. For most of its history it is estimated from the US-traded ADR ({adr_symbol}) and the EUR/USD rate; real XETRA closes are used for recent days where available.""",
        "drivers": """Earnings and guidance :: Quarterly results and what management expects next are usually the largest single driver of a share price.

Industry demand :: Spending in the company's main markets decides how fast it can grow.

Competition :: New rivals and pricing pressure can squeeze margins even when sales grow.

Interest rates :: Higher rates reduce what investors will pay for future profits, and hit fast-growing companies hardest.

Market mood :: In a broad sell-off most shares fall together, whatever their own results.""",
        "bull": """Sales and profits that beat expectations usually lift the shares.

New products or markets can open further growth.

Lower interest rates raise what investors will pay for future profits.""",
        "bear": """A weak quarter or a cut to guidance can move the shares sharply.

Competition can erode margins and market share.

A slowing economy reduces demand and weighs on profits.""",
        "risks": """Results can differ from expectations, and shares can gap on earnings days.

A single company carries more risk than a diversified fund.

Currency moves affect returns for investors outside the share's trading currency.""",
    },
    "etf_index": {
        "price_note": """?is_index_etf: The forecast is built on {code}, an exchange-traded fund that tracks {subject}. Fund prices and index points differ, so these figures are for the fund, not the index level.""",
        "drivers": """Company earnings :: An index rises over time when the profits of the companies in it grow.

Interest rates :: Higher rates make bonds more attractive and lower what investors pay for shares.

The largest members :: A few big companies can carry a weighted index on their own, in both directions.

The economy :: Growth, employment and inflation shape expectations for profits across sectors.

Market mood :: Fear and confidence move whole indices quickly, often faster than the news justifies.""",
        "bull": """Growing company profits have been the main long-term support for stock indices.

Rate cuts usually lift what investors will pay for shares.

Regular investment flows into index funds support demand.""",
        "bear": """A recession would cut profits across the index.

Higher rates or sticky inflation weigh on valuations.

Heavy weight in a few companies makes the index exposed to their results.""",
        "risks": """Indices can fall a long way in a bear market and take years to recover.

Fund fees and tracking differences reduce returns slightly.

Investors outside the fund's currency also carry currency risk.""",
    },
    "fx": {
        "drivers": """Interest rate differences :: Money tends to move toward the currency that pays more, so central bank decisions matter most.

Inflation :: Higher inflation erodes a currency's value and shapes what central banks do next.

Economic growth :: Stronger growth usually supports a currency through investment flows.

Trade balances :: Countries that sell more abroad than they buy see steady demand for their currency.

Risk appetite :: In times of stress, investors move toward currencies seen as safe.""",
        "bull": """A wider interest rate gap in the euro's favour would support the pair.

Stronger growth in the euro area would attract investment.

Easing inflation pressure in the euro area would help real returns.""",
        "bear": """Faster rate cuts by the European Central Bank would weigh on the euro.

Weak growth in the euro area would reduce demand for it.

Political stress in Europe tends to hurt the euro.""",
        "risks": """Exchange rates can move sharply on central bank decisions and political news.

Leveraged currency trading can lose more than the money put in.

Rates differ slightly between providers, and spreads add to the cost of trading.""",
    },
    "metal": {
        "drivers": """Interest rates and the dollar :: The metal pays no interest. Falling real rates and a weaker US dollar tend to lift it; rising rates and a strong dollar weigh on it.

Investment demand :: Buying and selling through funds, coins and bars can move the price quickly.

Safe-haven buying :: Investors often turn to precious metals in times of financial or political stress.

Supply :: New mine output responds slowly to price, so supply changes little from year to year.

Industrial and jewellery demand :: Physical use adds a steady layer of demand beneath investment flows.""",
        "bull": """Lower real interest rates reduce the cost of holding a metal that pays no income.

Political or financial stress tends to bring in safe-haven buyers.

Supply responds slowly, so stronger demand can lift the price.""",
        "bear": """Higher real rates make interest-paying assets more attractive.

A strong dollar usually weighs on metals priced in dollars.

Calm markets reduce safe-haven demand.""",
        "risks": """Physical coins and bars carry dealer premiums and storage costs; ETFs carry fees.

The metal produces no income, so returns depend entirely on the price.""",
    },
    "energy": {
        "drivers": """Global demand :: Economic activity, travel and industry set how much energy the world uses.

OPEC+ decisions :: Agreed output changes by major producers can shift the market quickly.

Inventories :: Weekly stock data show whether the market is tight or oversupplied.

Geopolitics :: Conflict or sanctions in producing regions can threaten supply and lift prices.

Seasons and weather :: Heating demand in winter and driving demand in summer shape the year.""",
        "bull": """Output cuts by major producers would tighten supply.

Disruption in a producing region can lift prices fast.

A stronger world economy raises demand for fuel.""",
        "bear": """A slowdown in the world economy would reduce demand.

Higher output from producers outside OPEC+ can leave the market oversupplied.

The long-term shift to electric transport and renewables weighs on future demand.""",
        "risks": """Energy prices are volatile and can move sharply on a single headline.

Funds that hold futures can drift from the spot price over time.

Prices are set in US dollars, so investors elsewhere also carry currency risk.""",
    },
}


def templates_for(class_code: str) -> dict[str, str]:
    return COMMON | CLASSES[class_code]
