"""Simple French/English i18n for the PyTalk Streamlit app.

Usage::

    from pytalk.i18n import t, language_selector

    language_selector()            # renders the sidebar selector
    st.title(t("brand.title"))     # looks up the current language's value
    st.write(t("greet.hello", name="Jean"))   # supports str.format kwargs

Missing keys fall back to English, then to the key itself — so the app never
crashes on a typo, it just shows the raw key.
"""
from __future__ import annotations

import streamlit as st

DEFAULT_LANG = "fr"
LANGUAGES = {"fr": "Français", "en": "English"}

TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── App-wide / navigation ───────────────────────────────────────────
    "nav.analysis":       {"en": "Analysis",       "fr": "Analyse"},
    "nav.portfolios":     {"en": "Portfolios",     "fr": "Portefeuilles"},
    "nav.custom_tickers": {"en": "Custom Tickers", "fr": "Symboles personnalisés"},
    "nav.screener":       {"en": "Screener",       "fr": "Filtre"},
    "nav.learning":       {"en": "Learning",       "fr": "Apprentissage"},
    "nav.info":           {"en": "Info",           "fr": "Infos"},
    "nav.logout":         {"en": "Logout",         "fr": "Déconnexion"},

    "lang.label": {"en": "Language", "fr": "Langue"},

    # ── Auth gate (App.py) ──────────────────────────────────────────────
    "auth.caption": {
        "en": "Family-only access. Sign in with your Microsoft / Hotmail / Outlook account.",
        "fr": "Accès réservé à la famille. Connectez-vous avec votre compte Microsoft / Hotmail / Outlook.",
    },
    "auth.signin": {
        "en": "Sign in with Microsoft",
        "fr": "Se connecter avec Microsoft",
    },
    "auth.denied": {
        "en": "Access denied for **{email}**.\n\nThis app is restricted to a family allowlist. Ask the app owner to add your email.",
        "fr": "Accès refusé pour **{email}**.\n\nCette application est réservée à une liste familiale. Demandez au propriétaire d'ajouter votre courriel.",
    },
    "auth.unknown_email": {"en": "(unknown email)", "fr": "(courriel inconnu)"},
    "auth.signout":       {"en": "Sign out",       "fr": "Se déconnecter"},

    # ── Brand / welcome ─────────────────────────────────────────────────
    "brand.caption": {
        "en": "Personal finance analysis — family edition.",
        "fr": "Analyse de finances personnelles — édition familiale.",
    },
    "brand.menu_intro": {
        "en": "Pick a section from the menu above:",
        "fr": "Choisissez une section dans le menu ci-dessus :",
    },
    "brand.menu_analysis": {
        "en": "**Analysis** — chart a ticker or a portfolio, run a backtest, get LLM commentary",
        "fr": "**Analyse** — graphique d'un symbole ou portefeuille, test rétroactif, commentaire du LLM",
    },
    "brand.menu_portfolios": {
        "en": "**Portfolios** — create and edit your own portfolios",
        "fr": "**Portefeuilles** — créez et modifiez vos propres portefeuilles",
    },
    "brand.menu_custom_tickers": {
        "en": "**Custom Tickers** — add tickers outside the built-in universe",
        "fr": "**Symboles personnalisés** — ajoutez des symboles hors de l'univers intégré",
    },
    "brand.menu_screener": {
        "en": "**Screener** — filter the universe by past performance and indicators",
        "fr": "**Filtre** — filtrez l'univers par performance passée et indicateurs",
    },
    "brand.menu_learning": {
        "en": "**Learning** — how each strategy works and when it makes sense",
        "fr": "**Apprentissage** — comment chaque stratégie fonctionne et quand l'utiliser",
    },
    "brand.menu_info": {
        "en": "**Info** — your session and runtime config",
        "fr": "**Infos** — votre session et la configuration d'exécution",
    },

    # ── Info page ───────────────────────────────────────────────────────
    "info.caption": {
        "en": "Who's signed in and what the app is running against right now.",
        "fr": "Qui est connecté et sur quoi l'application s'exécute en ce moment.",
    },
    "info.session":     {"en": "Session",       "fr": "Session"},
    "info.signed_in":   {"en": "Signed in as",  "fr": "Connecté en tant que"},
    "info.runtime":     {"en": "Runtime",       "fr": "Exécution"},
    "info.llm":         {"en": "LLM",           "fr": "LLM"},
    "info.database":    {"en": "Database",      "fr": "Base de données"},

    # ── Logout page ─────────────────────────────────────────────────────
    "logout.title":   {"en": "Sign out",                             "fr": "Déconnexion"},
    "logout.confirm": {"en": "Are you sure you want to sign out of PyTalk?",
                       "fr": "Êtes-vous sûr de vouloir vous déconnecter de PyTalk ?"},
    "logout.yes":     {"en": "Yes, sign out",                        "fr": "Oui, me déconnecter"},
    "logout.cancel":  {"en": "Cancel",                               "fr": "Annuler"},

    # ── Shared / sidebar controls ───────────────────────────────────────
    "common.source":          {"en": "Source",          "fr": "Source"},
    "common.source_single":   {"en": "Single ticker",   "fr": "Symbole unique"},
    "common.source_portfolio":{"en": "Portfolio",       "fr": "Portefeuille"},
    "common.type":            {"en": "Type",            "fr": "Type"},
    "common.ticker":          {"en": "Ticker",          "fr": "Symbole"},
    "common.custom_ticker":   {"en": "Custom ticker",   "fr": "Symbole personnalisé"},
    "common.portfolio":       {"en": "Portfolio",       "fr": "Portefeuille"},
    "common.lookback":        {"en": "Lookback (days)", "fr": "Historique (jours)"},
    "common.end_date":        {"en": "End date",        "fr": "Date de fin"},
    "common.strategy":        {"en": "Strategy",        "fr": "Stratégie"},
    "common.starting_cash":   {"en": "Starting cash",   "fr": "Capital initial"},
    "common.commission_bps":  {"en": "Commission (bps per trade)", "fr": "Commission (pb par transaction)"},
    "common.show_indicators": {"en": "Show indicators", "fr": "Afficher les indicateurs"},
    "common.rebalance_freq":  {"en": "Rebalance frequency", "fr": "Fréquence de rééquilibrage"},
    "common.reb_none":        {"en": "None (drift)",    "fr": "Aucun (dérive)"},
    "common.reb_monthly":     {"en": "Monthly",         "fr": "Mensuel"},
    "common.reb_quarterly":   {"en": "Quarterly",       "fr": "Trimestriel"},
    "common.reb_yearly":      {"en": "Yearly",          "fr": "Annuel"},
    "common.run_backtest":    {"en": "🧪 Run backtest", "fr": "🧪 Lancer le test rétroactif"},
    "common.clear_results":   {"en": "Clear results",   "fr": "Effacer les résultats"},
    "common.no_portfolios":   {"en": "No portfolios yet. Create one on the Portfolios page.",
                               "fr": "Aucun portefeuille. Créez-en un dans la page Portefeuilles."},
    "common.no_portfolios_here": {"en": "No portfolios yet. Create one above.",
                                  "fr": "Aucun portefeuille. Créez-en un ci-dessus."},
    "common.pick_ticker":     {"en": "Pick a ticker to begin.", "fr": "Choisissez un symbole pour commencer."},
    "common.pick_portfolio":  {"en": "Pick a portfolio to begin.", "fr": "Choisissez un portefeuille pour commencer."},
    "common.pick_ticker_err": {"en": "Pick a ticker.", "fr": "Choisissez un symbole."},
    "common.pick_portfolio_err": {"en": "Pick a portfolio.", "fr": "Choisissez un portefeuille."},
    "common.loading":         {"en": "Loading {name}…",  "fr": "Chargement de {name}…"},
    "common.no_data_range":   {"en": "No data for {ticker} in the selected range.",
                               "fr": "Aucune donnée pour {ticker} dans la période sélectionnée."},
    "common.no_holdings":     {"en": "Portfolio “{name}” has no holdings.",
                               "fr": "Le portefeuille « {name} » n'a aucune position."},
    "common.ticker_placeholder": {"en": "e.g. NESN.SW, 0700.HK", "fr": "ex. NESN.SW, 0700.HK"},
    "common.other":          {"en": "Other…", "fr": "Autre…"},

    # Asset type categories — keys match the internal CATEGORIES values in universe.py
    "cat.Custom Ticker":     {"en": "Custom Ticker", "fr": "Symbole personnalisé"},
    "cat.Stock":             {"en": "Stock",         "fr": "Action"},
    "cat.ETF":               {"en": "ETF",           "fr": "FNB"},
    "cat.Index":             {"en": "Index",         "fr": "Indice"},
    "cat.Commodity":         {"en": "Commodity",     "fr": "Matière première"},
    "cat.Crypto":            {"en": "Crypto",        "fr": "Cryptomonnaie"},

    # ── Analysis page ───────────────────────────────────────────────────
    "analysis.building_series": {"en": "Building “{name}” series…",
                                 "fr": "Construction de la série « {name} »…"},
    "analysis.title_portfolio": {"en": "Technical analysis for portfolio “{name}”",
                                 "fr": "Analyse technique du portefeuille « {name} »"},
    "analysis.title_ticker":    {"en": "Technical analysis for {ticker}",
                                 "fr": "Analyse technique de {ticker}"},
    "analysis.caption_portfolio": {
        "en": "Weighted buy-and-hold equity curve (rebased to 100 at range start). ",
        "fr": "Courbe d'équité d'achat-et-conservation pondérée (rebasée à 100 au début). ",
    },
    "analysis.no_overlap": {
        "en": "No overlapping price data across the portfolio's holdings.",
        "fr": "Aucune période commune dans les données de prix des positions du portefeuille.",
    },
    "analysis.past_perf":       {"en": "Past performance", "fr": "Performance passée"},
    "analysis.past_perf_caption": {
        "en": "**TR** = Total Return (price + reinvested dividends, retirement-relevant). "
              "**PR** = Price Return (split-adjusted, no dividends — matches Yahoo/Google).",
        "fr": "**TR** = Rendement total (prix + dividendes réinvestis, pertinent pour la retraite). "
              "**PR** = Rendement du prix (ajusté des fractionnements, sans dividendes — comme Yahoo/Google).",
    },
    "analysis.no_history":      {"en": "No historical data available.",
                                 "fr": "Aucune donnée historique disponible."},
    "analysis.loading_perf":    {"en": "Loading past performance…",
                                 "fr": "Chargement de la performance passée…"},
    "analysis.ytd":             {"en": "{year} YTD",      "fr": "{year} cumul annuel"},
    "analysis.validate_btn":    {"en": "🧠 Validate portfolio", "fr": "🧠 Valider le portefeuille"},
    "analysis.clear_validation":{"en": "Clear validation", "fr": "Effacer la validation"},
    "analysis.describe_btn":    {"en": "🧠 Describe current state",
                                 "fr": "🧠 Décrire l'état actuel"},
    "analysis.clear_snapshot":  {"en": "Clear snapshot",   "fr": "Effacer l'analyse"},
    "analysis.portfolio_value": {"en": "Portfolio value",  "fr": "Valeur du portefeuille"},
    "analysis.price":           {"en": "Price",            "fr": "Prix"},
    "analysis.volume":          {"en": "Volume",           "fr": "Volume"},
    "analysis.buy":             {"en": "Buy",              "fr": "Achat"},
    "analysis.sell":            {"en": "Sell",             "fr": "Vente"},
    "analysis.running_portfolio":{"en": "Running portfolio backtest…",
                                  "fr": "Test rétroactif du portefeuille en cours…"},
    "analysis.running_ticker":   {"en": "Running backtest on {ticker}…",
                                  "fr": "Test rétroactif de {ticker} en cours…"},
    "analysis.bt_failed":        {"en": "Backtest failed: {error}",
                                  "fr": "Échec du test rétroactif : {error}"},
    "analysis.bt_title_ticker": {"en": "Backtest — {ticker} with {strategy}",
                                 "fr": "Test rétroactif — {ticker} avec {strategy}"},
    "analysis.bt_title_portfolio": {"en": "Backtest — portfolio “{name}” with {strategy}",
                                    "fr": "Test rétroactif — portefeuille « {name} » avec {strategy}"},
    "analysis.skipped":         {"en": "Skipped (no data or failed backtest): {list}",
                                 "fr": "Ignoré (pas de données ou échec) : {list}"},
    "analysis.explain_btn":     {"en": "🧠 Explain this result",
                                 "fr": "🧠 Expliquer ce résultat"},
    "analysis.clear_explain":   {"en": "Clear explanation", "fr": "Effacer l'explication"},
    "analysis.per_ticker_results":{"en": "Per-ticker results", "fr": "Résultats par symbole"},
    "analysis.trades":          {"en": "Trades",         "fr": "Transactions"},
    "analysis.full_stats":      {"en": "Full stats",     "fr": "Statistiques complètes"},
    "analysis.raw_data":        {"en": "Raw data",       "fr": "Données brutes"},
    "analysis.metric_return":   {"en": "Return",         "fr": "Rendement"},
    "analysis.metric_bh":       {"en": "Buy & Hold",     "fr": "Achat-et-conservation"},
    "analysis.metric_sharpe":   {"en": "Sharpe",         "fr": "Sharpe"},
    "analysis.metric_mdd":      {"en": "Max Drawdown",   "fr": "Repli max."},
    "analysis.metric_final_eq": {"en": "Final Equity",   "fr": "Capital final"},
    "analysis.equity_label":    {"en": "Equity",         "fr": "Capital"},
    "analysis.drawdown_label":  {"en": "Drawdown %",     "fr": "Repli %"},

    # ── Backtest page (standalone) ──────────────────────────────────────
    "backtest.configure_hint": {
        "en": "Configure parameters in the sidebar, then click Run backtest.",
        "fr": "Configurez les paramètres dans la barre latérale puis cliquez sur Lancer.",
    },
    "backtest.title_ticker":    {"en": "Backtest for {label} with {strategy}",
                                 "fr": "Test rétroactif pour {label} avec {strategy}"},
    "backtest.title_portfolio": {"en": "Backtest for portfolio “{name}” with {strategy}",
                                 "fr": "Test rétroactif pour le portefeuille « {name} » avec {strategy}"},
    "backtest.trades":          {"en": "Trades",        "fr": "Transactions"},
    "backtest.per_ticker_trades":{"en": "Per-ticker trades", "fr": "Transactions par symbole"},
    "backtest.portfolio_stats": {"en": "Portfolio stats", "fr": "Statistiques du portefeuille"},
    "backtest.running":         {"en": "Running backtest…", "fr": "Test rétroactif en cours…"},
    "backtest.loading_prices":  {"en": "Loading prices…", "fr": "Chargement des prix…"},
    "backtest.sma_window_faber":{"en": "SMA window (trading days, ~21 per month)",
                                 "fr": "Fenêtre SMA (jours ouvrés, ~21 par mois)"},
    "backtest.sma_fast":        {"en": "Fast SMA",      "fr": "SMA rapide"},
    "backtest.sma_slow":        {"en": "Slow SMA",      "fr": "SMA lente"},
    "backtest.ema_fast":        {"en": "Fast EMA",      "fr": "EMA rapide"},
    "backtest.ema_slow":        {"en": "Slow EMA",      "fr": "EMA lente"},
    "backtest.signal_ema":      {"en": "Signal EMA",    "fr": "EMA signal"},
    "backtest.rsi_window":      {"en": "RSI window",    "fr": "Fenêtre RSI"},
    "backtest.oversold":        {"en": "Oversold",      "fr": "Survendu"},
    "backtest.overbought":      {"en": "Overbought",    "fr": "Suracheté"},
    "backtest.window":          {"en": "Window",        "fr": "Fenêtre"},
    "backtest.stddev":          {"en": "Std deviations", "fr": "Écarts types"},
    "backtest.stddev_entry":    {"en": "Std deviations (entry)", "fr": "Écarts types (entrée)"},
    "backtest.donch_entry":     {"en": "Entry window (N-day high)",
                                 "fr": "Fenêtre d'entrée (plus haut sur N jours)"},
    "backtest.donch_exit":      {"en": "Exit window (M-day low)",
                                 "fr": "Fenêtre de sortie (plus bas sur M jours)"},
    "backtest.vwap_window":     {"en": "VWAP window",   "fr": "Fenêtre VWAP"},

    # ── Portfolios page ─────────────────────────────────────────────────
    "portfolios.create_header":  {"en": "Create a portfolio", "fr": "Créer un portefeuille"},
    "portfolios.existing":       {"en": "Existing portfolios", "fr": "Portefeuilles existants"},
    "portfolios.name":           {"en": "Name",               "fr": "Nom"},
    "portfolios.name_placeholder":{"en": "e.g. Tech Megacaps", "fr": "ex. Grandes capitalisations tech"},
    "portfolios.save":           {"en": "Save portfolio",     "fr": "Enregistrer le portefeuille"},
    "portfolios.saved":          {"en": "Saved portfolio “{name}”.",
                                  "fr": "Portefeuille « {name} » enregistré."},
    "portfolios.weight":         {"en": "Weight",             "fr": "Poids"},
    "portfolios.add_holding":    {"en": "Add holding",        "fr": "Ajouter une position"},
    "portfolios.custom_placeholder":{"en": "Custom symbol",   "fr": "Symbole personnalisé"},
    "portfolios.use_picklist":   {"en": "Use picklist",       "fr": "Utiliser la liste"},
    "portfolios.remove":         {"en": "Remove",             "fr": "Retirer"},
    "portfolios.save_changes":   {"en": "Save changes",       "fr": "Enregistrer les modifications"},
    "portfolios.updated":        {"en": "Updated.",           "fr": "Mis à jour."},
    "portfolios.delete":         {"en": "Delete",             "fr": "Supprimer"},
    "portfolios.deleted":        {"en": "Deleted “{name}”.",  "fr": "« {name} » supprimé."},
    "portfolios.expander":       {"en": "{name} ({count} holdings)",
                                  "fr": "{name} ({count} positions)"},
    "portfolios.normalized":     {"en": "Normalized weights — {text}",
                                  "fr": "Poids normalisés — {text}"},
    "portfolios.validate_btn":   {"en": "🧠 Validate portfolio", "fr": "🧠 Valider le portefeuille"},
    "portfolios.clear_validation":{"en": "Clear validation",   "fr": "Effacer la validation"},
    "portfolios.save_first":     {"en": "Save the portfolio first, or fix zero weights.",
                                  "fr": "Enregistrez d'abord le portefeuille ou corrigez les poids nuls."},

    # ── Custom tickers page ─────────────────────────────────────────────
    "customticker.title":        {"en": "My Custom Tickers",
                                  "fr": "Mes symboles personnalisés"},
    "customticker.caption": {
        "en": "Your saved tickers outside the built-in universe. Tickers are added "
              "automatically when you type one via **Other…** in Analysis — or you can add "
              "them manually below. Yahoo's `quoteType` decides the category.",
        "fr": "Vos symboles enregistrés hors de l'univers intégré. Les symboles sont ajoutés "
              "automatiquement lorsque vous en saisissez un via **Autre…** dans Analyse — ou "
              "vous pouvez les ajouter manuellement ci-dessous. Le `quoteType` de Yahoo "
              "détermine la catégorie.",
    },
    "customticker.add_header":   {"en": "➕ Add a custom ticker manually",
                                  "fr": "➕ Ajouter un symbole personnalisé"},
    "customticker.symbol":       {"en": "Symbol", "fr": "Symbole"},
    "customticker.name_opt":     {"en": "Name (optional)", "fr": "Nom (facultatif)"},
    "customticker.name_placeholder":{"en": "e.g. Nestle SA", "fr": "ex. Nestle SA"},
    "customticker.add":          {"en": "Add", "fr": "Ajouter"},
    "customticker.enter_symbol": {"en": "Enter a symbol.", "fr": "Saisissez un symbole."},
    "customticker.detecting":    {"en": "Detecting category for {sym}…",
                                  "fr": "Détection de la catégorie pour {sym}…"},
    "customticker.added":        {"en": "Added **{sym}** under **{cat}**.",
                                  "fr": "**{sym}** ajouté sous **{cat}**."},
    "customticker.add_failed":   {"en": "Failed to add: {error}",
                                  "fr": "Échec de l'ajout : {error}"},
    "customticker.none_yet": {
        "en": "You haven't added any custom tickers yet. Either use the form above, "
              "or go to **Analysis** → Type = any → Ticker = **Other…** and type a symbol.",
        "fr": "Vous n'avez encore ajouté aucun symbole personnalisé. Utilisez le formulaire "
              "ci-dessus ou allez dans **Analyse** → Type = au choix → Symbole = **Autre…** "
              "et saisissez un symbole.",
    },
    "customticker.list_title":   {"en": "Your custom tickers ({total})",
                                  "fr": "Vos symboles personnalisés ({total})"},
    "customticker.list_caption": {"en": "Change a ticker's category with the dropdown, or remove with ✕.",
                                  "fr": "Modifiez la catégorie avec la liste déroulante ou retirez avec ✕."},
    "customticker.cat_line":     {"en": "**{cat}** — {n} ticker(s)",
                                  "fr": "**{cat}** — {n} symbole(s)"},
    "customticker.category":     {"en": "Category", "fr": "Catégorie"},
    "customticker.remove_help":  {"en": "Remove {sym}", "fr": "Retirer {sym}"},

    # ── Screener page ───────────────────────────────────────────────────
    "screener.title":            {"en": "Screener", "fr": "Filtre"},
    "screener.types":            {"en": "Types",    "fr": "Types"},
    "screener.run":              {"en": "Run screener", "fr": "Lancer le filtre"},
    "screener.pick_type":        {"en": "Pick at least one type.",
                                  "fr": "Choisissez au moins un type."},
    "screener.intro": {
        "en": "Pick one or more types in the sidebar and click **Run screener**. "
              "The first run fetches up to 10 years of prices and may take a few minutes; "
              "subsequent runs hit the local cache and are instant.",
        "fr": "Choisissez un ou plusieurs types dans la barre latérale et cliquez sur "
              "**Lancer le filtre**. Le premier lancement télécharge jusqu'à 10 ans de prix "
              "et peut prendre quelques minutes ; les lancements suivants utilisent le cache "
              "local et sont instantanés.",
    },
    "screener.no_data":          {"en": "No data for the selected types.",
                                  "fr": "Aucune donnée pour les types sélectionnés."},
    "screener.loaded":           {"en": "Loaded {count} tickers across {cats} — end date {end}.",
                                  "fr": "{count} symboles chargés dans {cats} — date de fin {end}."},
    "screener.loading_item":     {"en": "Loading {ticker}… ({i}/{total})",
                                  "fr": "Chargement de {ticker}… ({i}/{total})"},
    "screener.filters":          {"en": "Filters", "fr": "Filtres"},
    "screener.returns":          {"en": "Returns (%)", "fr": "Rendements (%)"},
    "screener.indicators":       {"en": "Indicators", "fr": "Indicateurs"},
    "screener.risk":             {"en": "Risk", "fr": "Risque"},
    "screener.vs_sma200":        {"en": "vs SMA 200 (%)", "fr": "vs SMA 200 (%)"},
    "screener.pos_52w":          {"en": "52-week position (%)", "fr": "Position sur 52 semaines (%)"},
    "screener.annual_vol":       {"en": "Annualized vol (%)", "fr": "Volatilité annualisée (%)"},
    "screener.exclude_na":       {"en": "Exclude rows missing the filtered metric",
                                  "fr": "Exclure les lignes sans la métrique filtrée"},
    "screener.exclude_na_help":  {"en": "When a row lacks a metric (e.g. 10y return for a young ETF), "
                                        "keep it unless this box is checked.",
                                  "fr": "Si une ligne manque d'une métrique (ex. rendement 10 ans "
                                        "pour un FNB récent), elle est conservée sauf si cette "
                                        "case est cochée."},
    "screener.min":              {"en": "Min", "fr": "Min"},
    "screener.max":              {"en": "Max", "fr": "Max"},
    "screener.sort_by":          {"en": "Sort by", "fr": "Trier par"},
    "screener.descending":       {"en": "Descending", "fr": "Décroissant"},
    "screener.results":          {"en": "Results — {shown} of {total}",
                                  "fr": "Résultats — {shown} sur {total}"},
}


def _current_lang() -> str:
    return st.session_state.get("lang", DEFAULT_LANG)


def t(key: str, **fmt: object) -> str:
    """Return the translation for ``key`` in the active language.

    Falls back to English, then to the key itself if neither is defined.
    Any ``**fmt`` kwargs are applied via :py:meth:`str.format`.
    """
    lang = _current_lang()
    entry = TRANSLATIONS.get(key, {})
    value = entry.get(lang) or entry.get("en") or key
    if fmt:
        try:
            return value.format(**fmt)
        except (KeyError, IndexError):
            return value
    return value


def category_label(cat: str) -> str:
    """Translate an internal asset-type category (e.g. 'ETF') for display."""
    return t(f"cat.{cat}")


def other_label() -> str:
    """Translated display label for the OTHER sentinel (keeps the sentinel itself in English)."""
    return t("common.other")


def language_selector(*, location: str = "sidebar") -> None:
    """Render the French/English selector and persist to ``st.session_state.lang``."""
    if "lang" not in st.session_state:
        st.session_state["lang"] = DEFAULT_LANG

    target = st.sidebar if location == "sidebar" else st
    codes = list(LANGUAGES.keys())
    current = st.session_state["lang"]
    idx = codes.index(current) if current in codes else 0
    picked = target.radio(
        t("lang.label"),
        codes,
        index=idx,
        format_func=lambda c: LANGUAGES[c],
        horizontal=True,
        key="_lang_selector",
    )
    if picked != current:
        st.session_state["lang"] = picked
        st.rerun()
