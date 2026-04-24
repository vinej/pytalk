from __future__ import annotations

import streamlit as st

from pytalk.i18n import DEFAULT_LANG


_CONTENT: dict[str, dict] = {
    "en": {
        "title": "Learning — strategies",
        "intro": """
The Backtest page offers eight strategies across two broad camps:

**Passive / allocation-oriented (realistic baselines for retail investors):**
- **Buy & Hold** — the benchmark everything else is measured against
- **Faber Trend Filter** — the one technical strategy with credible academic support for retirement drawdown control

**Active / trade-signal strategies (mostly educational — they rarely beat buy-and-hold):**
- **Trend-following** — *SMA Cross, MACD Cross*
- **Mean-reversion** — *RSI, Bollinger, VWAP*
- **Breakout** — *Donchian*

No strategy wins in every market. Parameter tuning and market regime matter as much as
the strategy choice. Always compare the backtest return against **Buy & Hold** to see
whether the strategy is actually adding value.
""",
        "buy_hold": {
            "title": "Buy & Hold — the baseline",
            "body": """
**What it does.** Buys the asset on day 1 and holds to the end of the backtest.
No signals, no parameters.

**Why it's here.** It's the benchmark every other strategy should be judged against.
If a more complex strategy doesn't beat Buy & Hold after costs, the added complexity
isn't earning its keep.

**For portfolios**, choosing Buy & Hold unlocks a **Rebalance frequency** setting
(Monthly / Quarterly / Yearly / None). Rebalancing resets each holding back to its
target weight on schedule — the realistic retail retirement workflow. No rebalancing
means the allocation drifts with performance, which is also a valid choice.

**Works best when…** the asset has a positive long-run drift (equities, diversified
index funds). Over 10+ years, this is usually the hardest strategy to beat.

**Watch out for…** the Max Drawdown. A +250% return looks great on paper until
you realize it came with a -55% peak-to-trough dip you had to sit through without
panic-selling. Drawdown tolerance is the real test of this strategy.
""",
        },
        "faber": {
            "title": "Faber Trend Filter — the retirement-friendly risk-off rule",
            "body": """
**What it does.** Holds the asset when its closing price is above the long-term
moving average (default: 200-day SMA, ~10 calendar months). Moves to cash when
price drops below. Re-enters when price crosses back above.

**How it works.** One of the few technical rules with credible academic evidence:
Mebane Faber's 2007 paper *"A Quantitative Approach to Tactical Asset Allocation"*
showed that a simple 10-month moving-average filter applied to major asset classes
produced roughly the same long-run return as buy-and-hold but with **about half
the drawdown**. The filter keeps you out of the worst parts of major bear markets
(2000–2002, 2008, early 2020, 2022) while letting trends run.

**Parameters**
- **SMA window** *(200)* — default is ~10 calendar months on daily bars, matching
  Faber's original paper. Shorter windows react faster (more whipsaws); longer
  windows are smoother (later entries and exits).

**Works best when…** bear markets are extended and visible in the trend (as in 2008
and 2022). The cost of small whipsaws in range-bound markets is more than paid back
by avoiding the 30–55% crashes.

**Works worst when…** volatile chop without a real bear market (the signal flickers
between in/out and you eat small losses from each switch). Also misses the fastest
rebounds — e.g., by the time price cleared the 200-SMA after March 2020, the S&P
had already recovered ~30%.

**Why this one matters for retirees.** During the withdrawal phase, sequence-of-
returns risk is the main threat: a big drawdown early in retirement permanently
damages the portfolio because you're selling into it for income. Reducing peak
drawdown from -55% to -25% is worth more than an extra 1% of annualized return.
This is the most defensible "technical strategy" for someone managing retirement
capital.
""",
        },
        "sma_cross": {
            "title": "SMA Cross — trend-following",
            "body": """
**What it does.** Buys when a fast simple moving average crosses *above* a slow one
(the "golden cross"), sells when it crosses *below* ("death cross").

**How it works.** Two moving averages of closing prices. Their crossover is a simple,
lagging proxy for a change in trend direction.

**Parameters**
- **Fast SMA** *(default 20)* — shorter lookback, reacts quickly to new prices.
- **Slow SMA** *(default 50)* — longer baseline that represents the broader trend.

**Works best when…** the asset is in a sustained, directional trend (multi-month
bull or bear markets).

**Watch out for…** choppy, sideways markets — crossovers happen repeatedly, each
one a small losing trade. This is the classic whipsaw problem.
""",
        },
        "macd_cross": {
            "title": "MACD Cross — trend-following with momentum",
            "body": """
**What it does.** Buys when the MACD line crosses *above* its signal line, sells
on the opposite cross.

**How it works.**
- **MACD line** = fast EMA − slow EMA (a measure of momentum)
- **Signal line** = EMA of the MACD line (smoother trigger)

Crossovers flag changes in the *rate of change* of price, not just direction.

**Parameters**
- **Fast EMA** *(12)* & **Slow EMA** *(26)* — the EMAs whose difference defines MACD.
- **Signal EMA** *(9)* — smoothing window that determines crossover timing.

**Works best when…** markets trend with medium-term momentum shifts. Usually gives
earlier signals than SMA Cross.

**Watch out for…** the signal line smooths but also delays entries — by the time
the crossover fires, part of the move is already gone. Also prone to whipsaws in
range-bound regimes.
""",
        },
        "rsi": {
            "title": "RSI Mean Reversion — buy the dip",
            "body": """
**What it does.** Buys when RSI drops below the *oversold* threshold, closes the
position when RSI rises above *overbought*.

**How it works.** The Relative Strength Index compares the size of recent gains
to recent losses on a 0–100 scale. Low RSI = price has fallen too far too fast.

**Parameters**
- **Window** *(14)* — lookback period for the gain/loss smoothing.
- **Oversold** *(30)* — buy trigger.
- **Overbought** *(70)* — exit trigger.

**Works best when…** the asset oscillates around a stable fair value — range-bound
blue chips, index ETFs in calm regimes.

**Watch out for…** strong trends. RSI can stay below 30 for weeks during a crash
(the "falling knife") or above 70 during a rally. Mean-reversion in a trending
market means repeatedly fighting the tape.
""",
        },
        "bollinger": {
            "title": "Bollinger Mean Reversion — fade the extremes",
            "body": """
**What it does.** Buys when price touches the lower band, shorts when it touches
the upper band, and exits as price reverts to the middle band.

**How it works.** Bands are drawn at *±k standard deviations* around a moving
average. Under normal conditions, roughly 95% of price action stays inside 2σ
bands — touches of the outer bands suggest statistical extremes.

**Parameters**
- **Window** *(20)* — SMA period for the middle band *and* the volatility lookback.
- **Std deviations (k)** *(2.0)* — band width. Wider bands = fewer, higher-conviction signals.

**Works best when…** volatility is stationary and price mean-reverts — think
commodity pairs, index rebalancing, or consolidating stocks.

**Watch out for…** breakouts. When price "rides the band" (repeated touches
without reverting), this strategy shorts into a rally or longs into a crash.
Volatility regime shifts break the statistical assumption.
""",
        },
        "vwap": {
            "title": "VWAP Reversion — volume-weighted anchor",
            "body": """
**What it does.** Buys when price falls a configurable distance *below* the rolling
Volume-Weighted Average Price, closes the position when price crosses back above VWAP.

**How it works.** VWAP weighs each bar's typical price *(H+L+C)/3* by its volume,
so heavily-traded prices pull the anchor more strongly than thin bars. Distance
from VWAP is a volume-aware measure of over-/under-pricing. The strategy enters
when the close is more than *k* standard deviations below VWAP and exits on
reversion through VWAP.

Two reasonable uses share the same signal:
- **Trend pullbacks** — in an uptrend, dips to VWAP are "cheap" entries that
  usually bounce.
- **Range fading** — in a sideways market, extreme distance from VWAP reverts.

**Parameters**
- **VWAP window** *(20)* — rolling lookback. On daily bars this is the equivalent
  of classic intraday VWAP (which resets each session).
- **Std deviations (k)** *(1.5)* — how far below VWAP price must go before entry.
  Smaller = more trades, lower conviction. Larger = fewer, stronger signals.

**Works best when…** the asset has meaningful, varying volume — individual
stocks, ETFs, liquid crypto. Volume is the whole point of VWAP.

**Watch out for…**
- Assets with no or flat volume (many indices like `^GSPC`, some futures) — VWAP
  collapses to a simple moving average and the strategy loses its edge.
- Downtrends — the strategy buys dips. Without a trend filter, it will repeatedly
  catch falling knives.
""",
        },
        "donchian": {
            "title": "Donchian Breakout — Turtle-style trend capture",
            "body": """
**What it does.** Goes long when price breaks above the *N-day* high. Exits when
price drops below the *M-day* low. Pure price action — no averages, no oscillators.

**How it works.** Made famous by the 1980s Turtle Traders. The N-day high is the
highest close over the last N sessions; breaching it signals the start of a new
directional move. A shorter exit window gives back less profit on reversal.

**Parameters**
- **Entry window (N)** *(20)* — the breakout trigger lookback. Larger = fewer but stronger signals.
- **Exit window (M)** *(10)* — the trailing-stop lookback. Usually smaller than N.

**Works best when…** markets experience occasional, powerful directional moves —
commodities, trending equities, crypto in bull/bear legs.

**Watch out for…** prolonged sideways markets. Each false breakout is a small
loss, and they add up quickly. Also: Donchian buys *after* the breakout, so
you're never catching the absolute low.
""",
        },
        "how_to_read": """
### How to read the backtest results

- **Return [%]** — total strategy return over the backtest period.
- **Buy & Hold [%]** — what a passive investor would have earned. If your strategy
  underperforms this, the complexity isn't paying off.
- **Sharpe Ratio** — return per unit of volatility. Rough guide: < 1 is mediocre,
  1–2 is good, > 2 is suspicious (check for overfitting).
- **Max Drawdown [%]** — worst peak-to-trough loss along the way. A strategy
  with high return but 60% drawdown is psychologically very hard to trade.

**A note on overfitting.** Tuning parameters until backtest returns look great
almost always produces worse live results. A robust strategy works across a range
of parameter values, not just one. If a small parameter tweak changes the outcome
dramatically, the strategy is brittle.
""",
    },

    "fr": {
        "title": "Apprentissage — stratégies",
        "intro": """
La page Test rétroactif propose huit stratégies réparties en deux grandes familles :

**Passives / orientées répartition (bases réalistes pour l'investisseur particulier) :**
- **Achat-et-conservation** — la référence à laquelle tout le reste se compare
- **Filtre de tendance Faber** — la seule stratégie technique avec un appui académique
  crédible pour limiter les reculs à la retraite

**Actives / fondées sur des signaux (surtout éducatives — elles battent rarement l'achat-et-conservation) :**
- **Suivi de tendance** — *Croisement SMA, Croisement MACD*
- **Retour à la moyenne** — *RSI, Bollinger, VWAP*
- **Cassure** — *Donchian*

Aucune stratégie ne gagne dans tous les marchés. Le réglage des paramètres et le régime
de marché comptent autant que le choix de la stratégie. Comparez toujours le rendement
du test rétroactif à **Achat-et-conservation** pour voir si la stratégie ajoute
réellement de la valeur.
""",
        "buy_hold": {
            "title": "Achat-et-conservation — la référence",
            "body": """
**Ce qu'elle fait.** Achète l'actif au jour 1 et le conserve jusqu'à la fin du test
rétroactif. Aucun signal, aucun paramètre.

**Pourquoi elle est là.** C'est le point de comparaison auquel toute autre stratégie
doit être confrontée. Si une stratégie plus complexe ne bat pas l'achat-et-conservation
après frais, la complexité ajoutée ne se justifie pas.

**Pour les portefeuilles**, choisir Achat-et-conservation débloque un réglage
**Fréquence de rééquilibrage** (Mensuel / Trimestriel / Annuel / Aucun). Le rééquilibrage
ramène chaque position à son poids cible selon le calendrier — le scénario réaliste
de retraite pour un particulier. Sans rééquilibrage, la répartition dérive avec la
performance, ce qui est aussi un choix valide.

**Fonctionne mieux quand…** l'actif a une dérive positive à long terme (actions,
fonds indiciels diversifiés). Sur 10 ans et plus, c'est généralement la stratégie
la plus difficile à battre.

**Attention à…** le repli maximal. Un rendement de +250 % a l'air superbe sur papier,
jusqu'à ce qu'on réalise qu'il s'est accompagné d'un recul de -55 % du sommet au
creux qu'il a fallu traverser sans vendre en panique. La tolérance au repli est
le véritable test de cette stratégie.
""",
        },
        "faber": {
            "title": "Filtre de tendance Faber — la règle de retrait de risque adaptée à la retraite",
            "body": """
**Ce qu'elle fait.** Conserve l'actif tant que son prix de clôture est supérieur à
la moyenne mobile de long terme (par défaut : MMS sur 200 jours, ~10 mois civils).
Passe en liquidités quand le prix passe en dessous. Rentre à nouveau quand le prix
repasse au-dessus.

**Comment ça marche.** C'est l'une des rares règles techniques avec un appui
académique crédible : le texte de Mebane Faber de 2007, *« A Quantitative Approach
to Tactical Asset Allocation »*, a montré qu'un simple filtre de moyenne mobile
sur 10 mois appliqué aux grandes classes d'actifs produisait à peu près le même
rendement long terme que l'achat-et-conservation, mais avec **environ la moitié
du repli**. Le filtre vous tient à l'écart des pires phases des grands marchés
baissiers (2000–2002, 2008, début 2020, 2022) tout en laissant courir les tendances.

**Paramètres**
- **Fenêtre SMA** *(200)* — la valeur par défaut équivaut à ~10 mois civils sur
  barres quotidiennes, comme dans l'article original de Faber. Des fenêtres plus
  courtes réagissent plus vite (plus de faux signaux) ; des fenêtres plus longues
  sont plus lisses (entrées et sorties tardives).

**Fonctionne mieux quand…** les marchés baissiers sont prolongés et visibles dans
la tendance (comme en 2008 et 2022). Le coût de petits faux signaux dans les
marchés sans direction est largement compensé par le fait d'éviter les chutes
de 30 à 55 %.

**Fonctionne moins bien quand…** le marché est volatil et sans direction nette
(le signal alterne entre dedans/dehors et on encaisse de petites pertes à chaque
bascule). Elle rate aussi les rebonds les plus rapides — par ex., au moment où
le prix a franchi le SMA 200 après mars 2020, le S&P avait déjà récupéré ~30 %.

**Pourquoi elle compte pour les retraités.** Pendant la phase de décaissement,
le risque de séquence de rendements est la principale menace : un grand repli
en début de retraite détériore durablement le portefeuille, car on vend dedans
pour générer du revenu. Ramener le repli maximal de -55 % à -25 % vaut plus qu'un
point de rendement annualisé supplémentaire. C'est la « stratégie technique » la
plus défendable pour gérer un capital de retraite.
""",
        },
        "sma_cross": {
            "title": "Croisement SMA — suivi de tendance",
            "body": """
**Ce qu'elle fait.** Achète quand une moyenne mobile simple rapide croise *au-dessus*
d'une moyenne lente (« golden cross »), vend quand elle croise *en dessous* (« death cross »).

**Comment ça marche.** Deux moyennes mobiles des prix de clôture. Leur croisement
est un indicateur simple et retardé d'un changement de direction de tendance.

**Paramètres**
- **SMA rapide** *(défaut 20)* — fenêtre courte, réagit vite aux nouveaux prix.
- **SMA lente** *(défaut 50)* — référence plus longue représentant la tendance générale.

**Fonctionne mieux quand…** l'actif est dans une tendance soutenue et directionnelle
(marchés haussiers ou baissiers de plusieurs mois).

**Attention à…** les marchés agités et sans direction — les croisements se répètent,
chacun donnant une petite transaction perdante. C'est le problème classique des
faux signaux.
""",
        },
        "macd_cross": {
            "title": "Croisement MACD — suivi de tendance avec momentum",
            "body": """
**Ce qu'elle fait.** Achète quand la ligne MACD croise *au-dessus* de sa ligne de
signal, vend au croisement opposé.

**Comment ça marche.**
- **Ligne MACD** = EMA rapide − EMA lente (mesure de momentum)
- **Ligne de signal** = EMA de la ligne MACD (déclencheur plus lisse)

Les croisements signalent des changements de la *vitesse* du prix, pas seulement
de sa direction.

**Paramètres**
- **EMA rapide** *(12)* et **EMA lente** *(26)* — les EMA dont la différence définit le MACD.
- **EMA signal** *(9)* — fenêtre de lissage qui détermine le moment des croisements.

**Fonctionne mieux quand…** les marchés tendent avec des changements de momentum
à moyen terme. Donne habituellement des signaux plus précoces que le croisement SMA.

**Attention à…** la ligne de signal lisse mais retarde aussi les entrées — quand
le croisement déclenche, une partie du mouvement est déjà passée. Elle est aussi
sujette aux faux signaux dans les régimes sans direction.
""",
        },
        "rsi": {
            "title": "Retour à la moyenne RSI — acheter le creux",
            "body": """
**Ce qu'elle fait.** Achète quand le RSI passe sous le seuil de *survente*, ferme
la position quand le RSI repasse au-dessus du seuil de *surachat*.

**Comment ça marche.** L'indice de force relative compare l'ampleur des gains
récents aux pertes récentes sur une échelle de 0 à 100. RSI bas = le prix a trop
baissé trop vite.

**Paramètres**
- **Fenêtre** *(14)* — période de lissage des gains/pertes.
- **Survente** *(30)* — déclencheur d'achat.
- **Surachat** *(70)* — déclencheur de sortie.

**Fonctionne mieux quand…** l'actif oscille autour d'une juste valeur stable —
valeurs sûres en range, FNB indiciels dans des régimes calmes.

**Attention à…** les tendances fortes. Le RSI peut rester sous 30 pendant des
semaines lors d'un krach (le « couteau qui tombe ») ou au-dessus de 70 pendant
un rallye. Le retour à la moyenne dans un marché en tendance, c'est lutter
continuellement contre le courant.
""",
        },
        "bollinger": {
            "title": "Retour à la moyenne Bollinger — fondre sur les extrêmes",
            "body": """
**Ce qu'elle fait.** Achète quand le prix touche la bande inférieure, vend à
découvert quand il touche la bande supérieure, et ferme quand le prix revient
à la bande médiane.

**Comment ça marche.** Les bandes sont tracées à *±k écarts types* autour d'une
moyenne mobile. En conditions normales, environ 95 % des mouvements de prix
restent à l'intérieur de bandes à 2σ — les touchers des bandes extérieures
suggèrent des extrêmes statistiques.

**Paramètres**
- **Fenêtre** *(20)* — période SMA pour la bande médiane *et* fenêtre de volatilité.
- **Écarts types (k)** *(2,0)* — largeur des bandes. Bandes plus larges = signaux
  moins nombreux mais à plus forte conviction.

**Fonctionne mieux quand…** la volatilité est stable et le prix revient à la
moyenne — pensez aux paires de matières premières, au rééquilibrage d'indices
ou aux actions en consolidation.

**Attention à…** les cassures. Quand le prix « longe la bande » (touchers
répétés sans retour), la stratégie vend à découvert dans un rallye ou achète
dans un krach. Les changements de régime de volatilité invalident l'hypothèse
statistique.
""",
        },
        "vwap": {
            "title": "Retour VWAP — ancrage pondéré par le volume",
            "body": """
**Ce qu'elle fait.** Achète quand le prix descend d'une distance configurable
*sous* le prix moyen pondéré par le volume (VWAP) glissant, ferme la position
quand le prix repasse au-dessus du VWAP.

**Comment ça marche.** Le VWAP pondère le prix typique de chaque barre *(H+B+C)/3*
par son volume, de sorte que les prix à gros volume tirent l'ancrage plus fort que
les barres à faible volume. La distance au VWAP est une mesure de sur-/sous-valorisation
consciente du volume. La stratégie entre quand la clôture est à plus de *k* écarts
types sous le VWAP et sort au retour au-dessus du VWAP.

Deux usages raisonnables partagent le même signal :
- **Replis de tendance** — dans une tendance haussière, les creux vers le VWAP sont
  des entrées « à bon prix » qui rebondissent généralement.
- **Fading en range** — dans un marché sans direction, un écart extrême au VWAP
  se résorbe.

**Paramètres**
- **Fenêtre VWAP** *(20)* — fenêtre glissante. Sur barres quotidiennes, équivalent
  du VWAP intrajournalier classique (qui se réinitialise à chaque séance).
- **Écarts types (k)** *(1,5)* — jusqu'où le prix doit descendre sous le VWAP
  avant l'entrée. Plus petit = plus de transactions, moins de conviction.
  Plus grand = moins de signaux, plus forts.

**Fonctionne mieux quand…** l'actif a un volume significatif et variable —
actions individuelles, FNB, cryptos liquides. Le volume est toute la raison
d'être du VWAP.

**Attention à…**
- Les actifs sans volume ou à volume plat (beaucoup d'indices comme `^GSPC`,
  certains contrats à terme) — le VWAP se réduit à une moyenne mobile simple
  et la stratégie perd son avantage.
- Les tendances baissières — la stratégie achète les creux. Sans filtre de
  tendance, elle attrape à répétition des couteaux qui tombent.
""",
        },
        "donchian": {
            "title": "Cassure Donchian — capture de tendance à la Turtle",
            "body": """
**Ce qu'elle fait.** Passe à l'achat quand le prix casse au-dessus du plus haut
sur *N jours*. Sort quand le prix passe sous le plus bas sur *M jours*.
Action sur les prix pure — aucune moyenne, aucun oscillateur.

**Comment ça marche.** Rendue célèbre par les Turtle Traders des années 1980.
Le plus haut sur N jours est la clôture la plus élevée des N dernières séances ;
son franchissement signale le début d'un nouveau mouvement directionnel. Une
fenêtre de sortie plus courte rend moins de profit au moment du retournement.

**Paramètres**
- **Fenêtre d'entrée (N)** *(20)* — fenêtre du déclencheur de cassure. Plus
  grande = signaux moins nombreux mais plus forts.
- **Fenêtre de sortie (M)** *(10)* — fenêtre du stop suiveur. Habituellement
  plus petite que N.

**Fonctionne mieux quand…** les marchés connaissent des mouvements directionnels
occasionnels et puissants — matières premières, actions en tendance, crypto en
phase haussière ou baissière.

**Attention à…** les longs marchés sans direction. Chaque fausse cassure est
une petite perte, et elles s'additionnent vite. De plus : Donchian achète
*après* la cassure, donc on n'attrape jamais le creux absolu.
""",
        },
        "how_to_read": """
### Comment lire les résultats du test rétroactif

- **Rendement [%]** — rendement total de la stratégie sur la période du test.
- **Achat-et-conservation [%]** — ce qu'aurait gagné un investisseur passif. Si
  votre stratégie fait moins bien, la complexité ne rapporte pas.
- **Ratio de Sharpe** — rendement par unité de volatilité. Repère approximatif :
  < 1 est médiocre, 1–2 est bon, > 2 est suspect (vérifiez le surajustement).
- **Repli max. [%]** — pire perte du sommet au creux pendant la période. Une
  stratégie avec un bon rendement mais un repli de 60 % est très difficile à
  suivre psychologiquement.

**Une note sur le surajustement.** Régler les paramètres jusqu'à obtenir de
superbes rendements de test rétroactif produit presque toujours de moins bons
résultats en conditions réelles. Une stratégie robuste fonctionne pour une
plage de valeurs de paramètres, pas pour une seule. Si un petit ajustement
change radicalement le résultat, la stratégie est fragile.
""",
    },
}


_lang = st.session_state.get("lang", DEFAULT_LANG)
_c = _CONTENT.get(_lang, _CONTENT["en"])

st.title(_c["title"])
st.markdown(_c["intro"])
st.divider()

_SECTIONS = ("buy_hold", "faber", "sma_cross", "macd_cross", "rsi", "bollinger", "vwap", "donchian")
for _i, _key in enumerate(_SECTIONS):
    _entry = _c[_key]
    with st.expander(_entry["title"], expanded=_i == 0):
        st.markdown(_entry["body"])

st.divider()
st.markdown(_c["how_to_read"])
