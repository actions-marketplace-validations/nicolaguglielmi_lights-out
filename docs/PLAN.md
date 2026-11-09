# lights-out — implementation plan

> **About this document.** This is the owner's working plan, kept in Italian as written. It started as the brief handed to Claude Code to build the repository, and it stays the brief for every milestone (`/milestone` reads it). Amendments, notes and corrections stay in place, dated, on purpose: the document is also the log of how each decision changed and why. The decisions themselves are recorded in English in [`docs/adr/`](adr/); what exists and runs today is described in the [README](../README.md) and in [`docs/reference.md`](reference.md). Where the plan names something that does not exist yet, it says so with a dated status note.

Piano da consegnare a Claude Code per costruire la versione Google-based della piattaforma di sviluppo agentico. *(Stato 2026-11-02: l'identità è cambiata con ADR 0029, vedi l'emendamento in §1: il prodotto è l'harness, lo stack Google è il target cloud opzionale.)* Il repo ha due pubblici: chi lo clona dopo un talk e lo fa girare sul portatile, e chi lo porta su un progetto GCP vero.

Il piano è in italiano perché lo leggi tu. **I contenuti del repo (README, commenti, commit, nomi) vanno scritti in inglese**: è pubblico e i talk sono anche in inglese.

---

## 1. Nome

**lights-out** — repo `lights-out`.

"Lights-out manufacturing" è il termine industriale per la fabbrica che gira completamente automatizzata, senza nessuno in reparto, quindi a luci spente. Dice 24/7 e "nessun umano a guardare" in due parole, e si spiega dal palco in cinque secondi.

Tagline repo: *Six agents ship it. One human turns the lights back on.*

**GO/NO-GO è il vocabolario della pipeline, non il nome del progetto.** Ogni gate stampa `GO` o `NO-GO` e l'ultima fase è il poll umano, come il flight readiness poll della NASA. Sullo schermo si legge `CANARY: NO-GO → rollback`, ed è la slide migliore del talk.

Nomi interni da usare nel codice: il control plane è `tower`, i worker sono `crew`, la pipeline di rilascio è `launchpad`, il gate umano è `go-for-launch`. Non estendere la metafora oltre questi quattro.

*Emendamento 2026-09-23 (ADR 0029).* **Cos'è il prodotto.** lights-out è un harness di autonomia governata: lascia che degli agenti facciano cambi a volume su un codebase di cui nessuno si fida, in sicurezza — ogni cambio passa gate numerici, resta nel perimetro che il ticket dichiara, torna indietro da solo su un verify NO-GO, e arriva in produzione attraverso una sola decisione umana. I sei ruoli sono la squadra di consegna dell'harness. Il valore è l'harness; il modello è sostituibile e lo è già. Lo stack Google è il target cloud opzionale (L2/L3), non l'identità. Il nome resta: "lights-out manufacturing" è il reparto che gira senza nessuno perché i sistemi di sicurezza sono fidati, e "one human turns the lights back on" è il gate umano — calza all'harness meglio di quanto calzasse a una fabbrica. Il talk è secondario. Il secondo arco è in §14.

---

## 2. La regola d'oro

**Chi clona il repo deve avere una demo funzionante in meno di 15 minuti, senza account GCP, senza carta di credito, senza chiedere niente a nessuno.**

Questa regola vince su qualunque altra scelta tecnica. In pratica significa:

- `git clone && ./go demo` deve arrivare fino al rollback automatico di un canary. A L0, senza nemmeno una API key. L0 non è una versione ridotta: è il prodotto completo, il cloud è opzionale (§3, ADR 0022).
- Niente mock nascosti. Se un pezzo è simulato, deve esserlo in modo esplicito e dichiarato nel README con una riga tipo "at L0 the canary is a weighted Envoy split, not Cloud Run revisions".
- Ogni livello superiore aggiunge integrazioni reali senza riscrivere il livello sotto. Gli script dei gate, le query delle metriche e le definizioni dei ruoli sono gli stessi a L0 e a L3.
- Se una dipendenza esterna non è accessibile a uno sconosciuto (Stitch, Antigravity Enterprise, quote a pagamento), quella dipendenza **non può stare nel percorso critico**. Deve produrre un artefatto che viene committato nel repo, così chi clona parte da quell'artefatto.

---

## 3. Livelli di integrazione

*Emendato 2026-09-20 (ADR 0022).* **Il locale è il prodotto, il cloud è un'aggiunta.** L0 non è il gradino più basso di una scala che porta a GCP: è la piattaforma completa, con tutte le capacità, senza account e senza chiave. L1 è lo stesso prodotto con un modello vivo. L2 e L3 esistono per chi vuole i servizi gestiti di Google al posto dei container: cambiano gli adapter, non le capacità.

Quattro profili (`profiles/l0.env` … `profiles/l3.env`), in due gruppi:

| | **Locale — il prodotto** | | **Cloud — opzionale** | |
|---|---|---|---|---|
| | L0 · Replay | L1 · Local | L2 · Cloud | L3 · Platform |
| Serve | podman rootless (podman machine su macOS) | + Gemini API key | + progetto GCP con billing | + quote Agent Engine |
| Modelli | risposte registrate (fixture) | Gemini API, `gemini-3.8-flash` | Gemini Enterprise Agent Platform (ex Vertex AI), `gemini-3.8-flash` | idem + thinking level per ruolo |
| Harness worker | replay | Gemini CLI headless in container | Gemini CLI su Cloud Run Job | + adapter Antigravity SDK |
| Git e PR | Gitea in compose | Gitea; GitHub per un repo attaccato (adapter a M21) | GitHub reale | GitHub reale |
| CI | `./go ci` e i gate della torre sulla PR, nessun runner (ADR 0060) | idem | GitHub Actions o Cloud Build | idem |
| Registry e firma | Zot locale, firma con chiave locale, verifica della firma nel launchpad prima dello staging | idem | Artifact Registry, firma con chiave KMS, verifica con la stessa cosign, Binary Authorization come seconda serratura | idem |
| Canary | Envoy weighted cluster | Envoy | Cloud Deploy → Cloud Run | + opzione GKE |
| Database dell'app | Postgres in compose | idem | Cloud SQL — **non scala a zero, unico costo fisso**: si ferma o si cancella fra un test e l'altro | idem |
| Metriche | Prometheus | Prometheus | Managed Prometheus + Cloud Monitoring | idem |
| Grafici della console | Grafana | Grafana | Cloud Monitoring | idem |
| Flag | flagd (file) | flagd | flagd su Cloud Run (file su GCS) o Unleash | idem |
| Eventi e stato | `spool` + `sqlite`, file sotto `.crew/` (ADR 0060) | idem | Pub/Sub + Firestore (adapter a M10) | + adapter Cloud Workflows |
| Agenti ADK | stub | ADK locale (`adk web`) | ADK su Cloud Run | Agent Engine + BigQuery analytics |
| Console | in compose, legge git e state store | idem | su Cloud Run, legge GitHub e Firestore | idem |
| Tempo al primo rollback | < 15 min | < 20 min | ~45 min (terraform apply) | ~90 min |

**Nessuna capacità esiste solo a L2.** Verificato riga per riga il 2026-09-20 (ADR 0022): l'unica capacità che il piano originale dava solo al cloud era il rifiuto di un'immagine non firmata (Binary Authorization). Senza l'equivalente locale, "niente arriva in produzione senza firma" varrebbe solo su GCP e L0 sarebbe una demo, non il prodotto. Quindi: la porta `Registry` firma a ogni livello (chiave locale generata a `./go up`, mai committata; chiave KMS a L2) e la porta `Delivery` verifica la firma prima di portare l'immagine in staging, a ogni livello. Workload Identity Federation e Secret Manager non sono capacità ma il modo in cui il cloud custodisce credenziali che il piano locale non ha: a L0 non c'è nessuna chiave, a L1 c'è la Gemini API key in `.env` e gli hook del harness ne bloccano l'accesso al worker.

*Precisazione 2026-09-20 (ADR 0025 §6, ADR 0027 §5):* chi verifica la firma è `core/launchpad.sh` attraverso la porta `Registry` (`verify.sh`), prima dello staging e con lo stesso comando cosign a ogni livello — chiave su file a L0/L1, chiave KMS a L2. Binary Authorization resta a L2 come seconda serratura imposta dalla piattaforma, non come l'implementazione della regola: il controllo *sigstore* di Binary Authorization, verificato il 2026-09-20, è solo continuous validation su GKE e Artifact Registry, non ammissione.

**Il costo di L2.** Tutto in L2 scala a zero tranne Cloud SQL. Il piano lo dichiara qui, `infra/README.md` lo ripete con il comando per fermare o cancellare l'istanza fra un test e l'altro, e `./go down PROFILE=l2` deve fermarla (non solo spegnere i servizi che scalano a zero da soli). In locale il database resta un container e il problema non esiste.

**Il README segue quest'ordine:** prima il quick start locale (`./go demo`, niente account); poi la tabella qui sopra con i due gruppi di colonne; poi il resto del prodotto (app, gate, piano L0, launchpad, console); la sezione GCP arriva dopo tutto questo, si apre con la frase "everything below is optional" e con la riga sul costo di Cloud SQL, e non compare nel quick start.

Due scelte che tengono in piedi la tabella:

- **PromQL ovunque.** L'app espone metriche OTel in formato Prometheus. La query che decide se il canary passa è un file solo, `verify/slo.promql`, e gira identica su Prometheus locale e su Managed Prometheus. È la riga più importante di tutto il progetto: senza, L0 e L2 divergono subito.
- **Gitea Actions usa la sintassi di GitHub Actions.** Gli stessi workflow YAML girano in locale e su GitHub. Se qualcosa non è supportato dal runner locale, va isolato in uno step separato e saltato con una condizione, non duplicato.

*Emendamento 2026-11-08 (ADR 0060):* il runner di Gitea Actions esce dal piano L0; il suo ultimo job, `image`, lo fa ora il passo di rilascio della torre, come per un repository attaccato. La promessa diventa "la stessa CI ovunque": i workflow girano su GitHub Actions, e il job `ci` esegue `./go ci`, lo stesso comando di un portatile. Pub/Sub e Firestore escono da L0 e L1 come default: al loro posto `spool` e `sqlite`, due file sotto `.crew/`; gli emulatori restano, opt-in.

---

## 4. Porte e adapter

Il nucleo non conosce nessun fornitore. Ogni integrazione sta dietro un'interfaccia con almeno due implementazioni, e la scelta avviene da variabile d'ambiente del profilo — eccetto `Workload`, scelto da `WORKLOAD=<path>` (default `app`), lo stesso a ogni livello (ADR 0030 §1).

| Porta | Adapter | Note |
|---|---|---|
| `AgentHarness` | `replay`, `gemini-cli`, `claude-code`, `codex`, `antigravity-cli`, `antigravity-sdk`, `adk` | esegue un ruolo su un workspace e restituisce artefatti |
| `CodeHost` | `gitea`, `github` | branch, PR, commenti, merge, stato di un commit e attesa di quello stato (`await.sh`, ADR 0025 §5); `github` esiste da M21 (ADR 0043), solo per un repo attaccato |
| `Tracker` | `file`, `github-issues`, `linear` | il ticket è la sorgente del lavoro; `file` legge e scrive: `get.sh` e, da M22, `put.sh <titolo> <origine>` (corpo su stdin, idempotente sull'origine) |
| `EventBus` | `spool`, `pubsub-emulator`, `pubsub` | `spool` (default a L0 e L1, ADR 0060): una coda in un file SQLite sotto `.crew/`; gli emulatori opt-in; `pubsub` stesso codice dell'emulatore, cambia l'endpoint |
| `StateStore` | `sqlite`, `firestore-emulator`, `firestore` | stato del workflow, idempotenza; `sqlite` (default a L0 e L1, ADR 0060): un file sotto `.crew/` che sopravvive a `./go down` |
| `Orchestrator` | `inproc`, `cloud-workflows` | macchina a stati del ciclo di vita del ticket |
| `Delivery` | `envoy-canary`, `cloud-deploy`, `argo-rollouts` | quattro verbi: `deploy.sh <version> <image>`, `shift.sh <pct>`, `rollback.sh`, `status.sh`; **plugin**: si carica da `DELIVERY=` nel profilo, aggiungerne uno = una cartella + una riga, zero modifiche a `core/` (ADR 0024); ogni adapter passa la suite di conformità `gates/delivery-conformance.sh` (ADR 0026) |
| `Metrics` | `promql`, `prometheus`, `managed-prometheus` | stessa query PromQL; `promql` interroga `METRICS_URL`; `prometheus` ne è il caso del piano a `http://$PLANE_HOST:9090`, non `prometheus:9090`, che il workbench non risolve |
| `Flags` | `flagd`, `unleash` | OpenFeature, l'SDK non cambia; due verbi per il nucleo e i target: `evaluate.sh <flag> [version]`, `set.sh <flag> <variant>` (ADR 0026 §3) |
| `Registry` | `zot`, `artifact-registry` | `publish.sh <tag>` costruisce, firma e pusha stampando il riferimento immutabile; `verify.sh <tag>` verifica la firma e stampa il digest verificato (ADR 0025 §1) |
| `Charts` | `grafana`, `cloud-monitoring` | i grafici che la console mostra; la console non li ridisegna (ADR 0023) |
| `Workload` | `app`, `workloads/minimal` | ciò su cui la piattaforma opera, scelto da `WORKLOAD=<dir>` (default `app`), non dal profilo; `workload.env`, `compose.yaml`, `/healthz` e `/metrics` su `:8000`, `flags/flags.json`, `smoke.sh`, `load.sh`, runner in-image test/mutation/SAST, `fixtures/gates/`; non nominato in `core/`, `gates/`, `verify/`, `adapters/` (`ci/app-free.sh`); verificato da `ci/workloads.sh` e `./go demo-seam` (ADR 0030) |

*Stato 2026-11-02:* esistono `replay`, `gemini-cli`, `adk`, `gitea`, `file`, `pubsub-emulator`, `firestore-emulator`, `inproc`, `envoy-canary`, `promql`, `prometheus`, `flagd`, `zot` e i workload `app` e `workloads/minimal`. Gli altri nomi della tabella non sono ancora scritti e sono da implementare, ciascuno nella milestone che lo porta:

| Adapter | Porta | Milestone |
|---|---|---|
| `artifact-registry`, `cloud-deploy`, `managed-prometheus`, flagd su Cloud Run | Registry, Delivery, Metrics, Flags | M8, track cloud (il percorso di rilascio su GCP) |
| `pubsub`, `firestore`, `github-issues`, `cloud-workflows` | EventBus, StateStore, Tracker, Orchestrator | M10 (la tower gira su GCP) |
| `github` | CodeHost | M21 (GitHub come code host, ADR 0043) |
| `grafana`, `cloud-monitoring` | Charts | M11 (console) |
| `antigravity-sdk`, `linear`, `unleash` | AgentHarness, Tracker, Flags | da assegnare: ognuno con un ADR e la sua suite di conformità |
| `argo-rollouts` | Delivery | M25 (Kubernetes con Argo Rollouts, ADR 0051) |

Regola: **un adapter non può introdurre concetti nuovi nel nucleo.** Se Cloud Deploy ha un concetto che Envoy non ha, o lo si modella in astratto o resta dentro l'adapter.

*Emendamento 2026-09-20 (ADR 0024):* la regola è provata, non solo dichiarata. `ci/vendor-free.sh` fallisce se un file di `core/` nomina un fornitore di Delivery (Envoy, Cloud Deploy, Argo), anche in un commento. Il contratto di un adapter Delivery è la suite di conformità: promuove (staging → 5% → 25% → 100%), boccia e torna indietro su verify NO-GO, rispetta il freeze, riporta lo stato (`status.sh`: versione stabile, versione canary, peso). `envoy-canary` la passa oggi; `cloud-deploy` la passa come criterio di M8; è il requisito d'ingresso per qualunque adapter futuro. Il motore di container resta una scelta dell'utente, non un adapter: podman è il riferimento, docker è supportato e provato da `./go engine-compat` (ADR 0004, ADR 0012 §4).

*Emendamento 2026-09-20 (ADR 0026):* `ready.sh` **non è un verbo della porta `Delivery`**: è la sonda di readiness che ogni adapter presente in `PLANE_ADAPTERS` deve a `make up`, qualunque sia la sua porta (ADR 0012 §6). La suite di conformità non la chiama mai. `status.sh` stampa un solo oggetto JSON con esattamente tre chiavi — `stable` (stringa), `canary` (stringa o `null`), `weight` (intero 0–100) — e niente altro: quello che un fornitore vuole aggiungere va su stderr. La lista di parole di `ci/vendor-free.sh` cresce con `flagd|unleash`, perché il freeze esce da `core/launchpad.sh` e passa dietro la porta `Flags`.

*Emendamento 2026-11-03 (ADR 0037):* un workload può stare in un repository suo. `./go attach <path>` lo clona in `.attached/`, che diventa il `WORKLOAD` di default; il contratto di un workload attaccato sta in `.lights-out/` alla radice del suo repository (`workload.env`, frammento compose, `flags/`, `smoke.sh`, `load.sh`, `fixtures/gates/`, `worker.md`, `policy.env`, `tickets/`), quello di un workload dentro lights-out resta nella sua cartella (`app/`). La riga `Workload` della tabella vale per entrambi; `workloads/minimal` è ora un repo attaccabile, provato da `./go demo-seam`.

*Emendamento 2026-11-07 (ADR 0050):* `AgentHarness` guadagna `antigravity-cli`, Antigravity CLI (`agy`) 1.5.1, solo Gemini, **opzionale e sperimentale**: si sceglie solo con `AGENT_HARNESS=antigravity-cli`, e `gemini-cli` resta il default per `gemini` finché un run live di agy sul ticket 0001 non passa i gate. Un provider può quindi avere più di un harness (emenda ADR 0041 §2). Il binario è proprietario e senza licenza: pinnato per versione e sha256 per architettura in `release.env`, scaricato solo al build dell'immagine, mai pubblicato; il proxy di egress nega telemetria e auto-update, ed è questo a tenere fermo il pin. Il guard è lo stesso `guard.sh`, dietro uno shim, con un nome di hook casuale a ogni run; passa `./go harness-conformance` (casi 0–9) contro il modello scriptato. **Buco aperto, registrato e non chiuso:** gli hook `SessionStart` e `PreToolUse` del `.agents/hooks.json` del repository girano dentro il container, fuori dal guard; non possono spegnerlo né scavalcarne il deny, ma girano (ADR 0050 §7).

---

## 5. Decisioni già prese

### Chi scrive il codice
**`gemini-3.8-flash`** tramite **Gemini CLI in headless** (`gemini -p "..." --output-format json`), eseguito dentro un container per ogni task. Gemini CLI è Apache 2.0, ha `GEMINI.md` per le istruzioni di progetto, extension, skill, hook, custom command e client MCP: è l'equivalente dell'harness che serve, ed è l'unico clonabile da uno sconosciuto.

**Attenzione, cambiato da poco:** dal 18 giugno 2026 Google non serve più le richieste di Gemini CLI per Gemini Code Assist individuale, Google AI Pro e Ultra, e ha rimosso il "Login with Google" personale, indirizzando gli individui su Antigravity CLI. Quindi il percorso documentato per chi clona è **Gemini API key** (free tier intorno a 250 richieste al giorno, solo modelli Flash) oppure Vertex AI. Il README deve dirlo in modo esplicito, altrimenti il primo che prova si blocca sull'autenticazione e scrive una issue.

**Un solo modello per tutti i ruoli, la leva è il thinking level.** Gemini 3.8 Flash (2 settembre 2026): finestra da 1M token, tre livelli di thinking. Sui task lunghi consuma più token, quindi il thinking si fissa per ruolo e il budget di token si misura, non si stima.

*Emendamento 2026-11-03 (§16, M18):* un solo modello **alla volta**, scelto dal profilo con `MODEL_PROVIDER` e `MODEL` (Gemini, Claude o OpenAI), non più `gemini-3.8-flash` per definizione. La tabella del thinking qui sotto resta la leva per ruolo; la mappa verso il parametro di ogni fornitore sta nell'adapter.

Quindi `thinking` diventa un campo della definizione del ruolo, accanto a budget di token, timeout e iterazioni massime:

| Ruolo | thinking | perché |
|---|---|---|
| dev worker | high | task lungo, molti tool, va verificato |
| test e review | high | deve trovare quello che l'autore non ha visto |
| architect | high | poche chiamate, alto impatto |
| product | medium | conversazione, non esecuzione |
| release brief | low | formatta dati che ha già |
| ops triage | low | volumi alti, latenza conta, è il caso d'uso citato per le pipeline di incident response |

Conseguenza operativa: a L1 il free tier limita ai modelli Flash e a un tetto giornaliero di richieste, che con 3.8 Flash basta se i task del demo restano piccoli e il thinking resta basso. La demo dal palco gira a L2, dove alzi il thinking e non hai il tetto. *(Stato 2026-11-02: L2 non è ancora implementato; la demo gira a L0, e a L1 con la chiave.)*

*Nota 2026-09-16 (ADR 0018):* fino al secondo run reale del 16 settembre questa tabella era decorativa. Con Gemini CLI 0.59.0 il thinking per ruolo non è mai stato applicato: la CLI rimappava la richiesta a `gemini-3.5-flash` prima di consultare l'alias su cui `THINKING` viaggia, e la fixture di ticket 0001 è registrata col thinking di default. Il pin alla 0.61.0-preview.0 (ADR 0018) è il primo runtime in cui la leva è davvero collegata; i budget in `roles/dev-worker/role.env` sono stati rimisurati lì.

### Con cosa lo costruisci tu
Da non confondere con il precedente: i modelli qui sotto servono a **scrivere questo repo** con Claude Code, non girano mai a runtime. La ripartizione sta nel frontmatter dei subagent in `.claude/agents/`, così non devi ricordartela ogni sessione.

| Lavoro | Modello |
|---|---|
| Plan mode, ADR, nucleo porte/adapter, risk scoring, bug trasversali | `opus` |
| Il 10% davvero difficile, dove Opus ha già mancato due volte | `fable` |
| Implementazione di una milestone già specificata, adapter, test | `sonnet` |
| Rinomine, docstring, scaffolding, commit message | `haiku` |

`CLAUDE_CODE_SUBAGENT_MODEL` sovrascrive il modello di tutti i subagent: usalo come tetto di spesa quando serve, non come default.

*Nota 2026-11-04, decisione dell'owner:* il modello minimo di costruzione è `sonnet`, anche per rinomine e commit message (la riga `haiku` qui sopra non si usa più); su Sonnet l'effort è `xhigh` ovunque il ragionamento serva, basso solo nei run di accettazione. L'assegnazione per milestone del terzo arco (modello della sessione, subagent, effort per fase) è in [`docs/plans/third-arc-execution.md`](plans/third-arc-execution.md); la tabella degli effort che la skill `/milestone` applica sta in `.claude/skills/milestone/SKILL.md`.

### Antigravity
*Stato 2026-11-02: non usato. L'adapter `antigravity-sdk` non esiste ancora (tabella in §4); la superficie umana descritta qui sotto non è nel repo.*

Antigravity 2.0 (I/O 2026) è una piattaforma su cinque superfici: app desktop, CLI, SDK Python sull'harness degli agenti, Managed Agents nella Gemini API (fatturati per run, non per token) ed Enterprise Agent Platform. Dove lo usiamo:

- **Superficie umana**: il Manager per orchestrare e osservare gli agenti mentre lavorano, con il repo aperto. È quello che mostri sul palco quando fai vedere i worker in parallelo.
- **Adapter opzionale** `antigravity-sdk` per l'harness, dietro la stessa porta di Gemini CLI, così il confronto tra i due è una variabile d'ambiente e diventa una slide.
- **Non** come control plane e **non** nel percorso critico del repo clonabile: è in public preview, i limiti del piano gratuito sono già stati tagliati una volta, la CLI su Linux è indicata come preview e i Managed Agents si pagano a run. Va bene per la demo, non per la riproducibilità.

### Stitch
*Stato 2026-11-02: non usato. Arriva con la console (M11); `design/` non esiste ancora.*

Stitch genera UI da prompt, esporta HTML/Tailwind, React, Vue, Angular, Flutter e SwiftUI, incolla in Figma con layer e Auto Layout, e dall'aggiornamento di marzo 2026 espone un **server MCP** che si collega agli strumenti di coding. Resta però un esperimento di Google Labs, nel browser, gratuito con un tetto mensile di generazioni e senza API stabile.

Quindi entra così: il server MCP di Stitch si collega all'**agente interattivo** (Antigravity o Gemini CLI in sessione), che è il design step con l'umano dentro. Il risultato viene committato come artefatto: `design/tokens.json`, gli screen esportati in Tailwind sotto `design/screens/`, e un `design/CONTRACT.md` che elenca i componenti e gli stati. Il frontend worker headless legge quegli artefatti come spec e non chiama mai Stitch. Chi clona il repo trova i design già dentro e ottiene una UI funzionante senza aprire Stitch.

*Emendamento 2026-09-20 (ADR 0023):* **il soggetto del design loop è la console, non l'app di esempio.** Le cinque schermate di M11 si progettano con Stitch e i loro artefatti vanno in `design/`; il frontend dell'app bersaglio resta com'è (ADR 0009) e non è più il destinatario di `design/CONTRACT.md`.

### Gli agenti ADK
ADK copre i ruoli che non toccano il repo: product agent (dialogo lungo con il PO, sessioni e memoria), triage agent (volumi alti, un modello Flash basta), release agent (prepara il promotion brief). Motivi concreti: flusso di conferma dei tool per l'human-in-the-loop, possibilità di riavvolgere una sessione, analytics su BigQuery con provenienza delle tool call, e `adk eval` che usiamo come test di regressione degli agenti. A L3 girano su Agent Engine, sotto girano in locale.

Pinnare le versioni: ADK ha due linee di release attive, la 2.x e la 1.x. Scegliere la 2.x, fissare la versione esatta, e far passare `adk eval` prima di ogni bump.

*Nota 2026-09-16 (M7, ADR 0020):* ADK 2.x è pinned a 2.9.1, `adk eval` a L0 gira sul modello replay.

### Il control plane
Resta noioso di proposito: eventi su Pub/Sub, dispatcher, macchina a stati con lo stato su Firestore, worker come job effimeri. Entrambi hanno un emulatore ufficiale, quindi L0 e L2 condividono il codice. Cloud Workflows entra come adapter alternativo a L3, non come base.

### L'app bersaglio
Serve un'applicazione vera su cui gli agenti lavorano. Deve essere abbastanza piccola da leggersi in un'ora e abbastanza vera da avere tutto ciò che rompe: **un backend Python (FastAPI) con Postgres, un frontend React, autenticazione, una migrazione di schema, un endpoint dipendente da un servizio esterno** (così esiste un contract test). Dominio suggerito: gestione iscrizioni a un meetup, che è anche il dominio che conosci meglio e regge bene sul palco.

*Emendamento 2026-09-23 (ADR 0029).* L'app meetup è il **primo workload**, non il soggetto fisso del prodotto. Da M12 sta dietro una porta (ADR 0030 ne fissa nome e contratto): nessun file di `core/`, `gates/`, `verify/` o `adapters/` la nomina, `ci/app-free.sh` lo prova, e un secondo workload deliberatamente minimo dimostra che il seam è reale. Misura del 2026-09-22: ~87 riferimenti all'app in 15 file fuori da `app/`, `core/crew.sh` compreso.

*Emendamento 2026-09-23 (ADR 0030).* Nome e contratto della porta `Workload`: una directory scelta da `WORKLOAD=<path>` (default `app`), sette chiavi in `workload.env`, tre servizi compose fissi (`backend`, `backend-canary`, `backend-test`), `/healthz` e `/metrics` su `:8000`, un file di flag, due runner in-image (test/mutation, SAST), `fixtures/gates/`. `adapters/` entra nel perimetro di `ci/app-free.sh` insieme a `core/`, `gates/`, `verify/`: `adapters/flagd/ready.sh` interrogava il flag `waitlist` per nome, che il secondo workload non ha. `workloads/minimal/` è quel secondo workload, provato da `./go demo-seam`.

---

## 6. Layout del repo

```
lights-out/
  LICENSE                   # Apache 2.0
  NOTICE                    # copyright
  README.md                 # tabella dei livelli in cima, 15 minuti al primo rollback
  Makefile                  # up, demo, demo-rollback, e2e, clean, per ogni livello
  go                        # unico entrypoint host, POSIX sh
  profiles/                 # l0.env … l3.env
  workbench/                # Containerfile della toolchain (+ cloud/ per gcloud e terraform, ADR 0028)
  ci/                       # self-check del repo
  core/                     # nucleo senza fornitori: modello artefatti, macchina a stati, risk scoring
  adapters/                 # una cartella per adapter della tabella §4: codice e config del vendor (anche envoy-canary e cloud-deploy)
  roles/                    # un ruolo = una cartella: GEMINI.md, prompt, tool ammessi, skill, hook
    product/ architect/ dev-worker/ test-reviewer/ release/ ops-triage/
  policy/                   # policy-as-code condivisa: cosa serve per mergiare, promuovere, chi tocca cosa
  gates/                    # script dei gate, containerizzati, identici a L0 e L3
  verify/                   # slo.promql e il verify runner
  tickets/                  # i ticket del progetto, uno per file, la sorgente del lavoro a L0 (Tracker=file)
  design/                   # artefatti Stitch committati per la console: tokens, screens, CONTRACT.md
  console/                  # M11: la vista sulla piattaforma, legge git e state store, scrive due cose sole
  app/                      # l'applicazione bersaglio: il primo workload (ADR 0030)
  workloads/                # altri workload che provano il seam (M12, ADR 0030): minimal/
  infra/                    # terraform per L2 e L3
  fixtures/                 # risposte modello registrate per L0
  e2e/                      # il golden path
  docs/                     # architettura, ADR, guida al talk
```

*Emendamento 2026-09-20 (ADR 0023):* aggiunta `console/`; `design/` descrive la console, non l'app bersaglio (ADR 0009 emendato).

*Emendamento 2026-09-23 (ADR 0030):* aggiunta `workloads/`, il secondo workload che prova il seam della porta `Workload`.

*Correzione 2026-09-14 (M2, ADR 0012):* la prima versione di questo layout aveva anche `delivery/ # envoy/ e clouddeploy/`, che duplicava gli adapter `envoy-canary` e `cloud-deploy` della tabella §4. Vince §4: la config di Envoy sta in `adapters/envoy-canary/`, quella di Cloud Deploy starà in `adapters/cloud-deploy/`, e `delivery/` non esiste. Aggiunta `tickets/`, che il layout non prevedeva.

---

## 7. Milestone

Ordine scelto apposta: **prima la rete di sicurezza, poi i gate, i worker per ultimi.** Quando il primo agente apre la prima PR, il canary e il rollback esistono già.

Ogni milestone chiude con il repo verde e una demo eseguibile. Nessuna milestone può lasciare `make demo` rotto.

### M0 — Scheletro
Repo, Makefile, profili, CI del repo stesso, README con la tabella dei livelli e un `docs/ARCHITECTURE.md` che spiega porte e adapter.
**Fatto quando:** `./go help` elenca i target, la CI passa su un repo vuoto, il README dice la verità su cosa esiste.

### M1 — App bersaglio
FastAPI + Postgres + React, metriche OTel in formato Prometheus, flag OpenFeature con un flag di esempio, migrazione in stile expand/contract, un contract test verso un servizio finto.
**Fatto quando:** `./go up` la avvia in compose, `/metrics` espone error rate e latenza, i test passano.

### M2 — Piano locale (L0)
Compose con Gitea + act runner, registry Zot, Envoy con due cluster pesati, Prometheus, flagd, emulatori Pub/Sub e Firestore.
**Fatto quando:** `./go up` alza tutto, apri Gitea su localhost, l'app risponde dietro Envoy, Prometheus scrape le metriche.

### M3 — Delivery, canary, rollback, kill switch
Il controller di rilascio con le fasi (staging, 5%, 25%, 100%), il verify runner che esegue `verify/slo.promql` e confronta canary contro stabile, il rollback automatico, il freeze globale e il kill switch via flag.
**Fatto quando:** `./go demo-rollback` a L0, senza nessuna chiamata a un modello, rilascia una versione che fallisce il verify e torna indietro da sola, e il log mostra la decisione con i numeri che l'hanno prodotta. `./go demo-hold` prova il ramo opposto sulla stessa release: flag spento, verify in GO ad ogni fase, canary tenuto al 25% invece di essere ritirato in silenzio.

*Nota 2026-09-14 (M3, ADR 0014):* `demo-hold` non era nel testo originale di questa milestone. Aggiunto perché un verify runner cablato per bocciare sempre passerebbe comunque `demo-rollback`, e quel gate sarebbe rotto senza che nessuno se ne accorga: serve la prova di entrambe le direzioni, non solo del rollback. Resta un comando manuale, fuori dalla lista fissa di `./go demo` (ADR 0003) — il criterio del golden rule riguarda il rollback, non la promozione.

### M4 — Gate in CI
Unit, integration con testcontainers, contract test, mutation testing con soglia, SAST, scan dipendenze, secret scan. Lo script di risk scoring che classifica la PR (auth, pagamenti, migrazioni, dimensione del diff) e decide auto-merge o seconda review.
**Fatto quando:** una PR con un test finto viene bocciata dal mutation score; una PR che tocca una migrazione viene marcata ad alto rischio e non si auto-mergia.

*Nota 2026-09-15 (M4, ADR 0015):* i test di integrazione restano su Postgres da compose (ADR 0010), non testcontainers, per decisione esplicita; "una PR" a L0 è un git range (due o più commit con `git merge-base`), non una vera PR Gitea/GitHub (quella arriva a M5). Il comando di accettazione è `./go demo-gates` sulle sei fixture committate; ogni fixture è una patch git-format-patch applicata in un worktree usa e getta, con i verdetti attesi registrati in `expect`.

### M5 — Runtime degli agenti (L1)
La porta `AgentHarness` con adapter `replay` e `gemini-cli`. Le definizioni dei sei ruoli. Gli hook che bloccano push su main, comandi distruttivi e accesso a segreti. Il worker in container con budget di token, timeout e massimo di iterazioni, che termina aprendo una PR.
**Fatto quando:** a L1, con una Gemini API key, assegni un ticket e nasce una PR che passa la CI di M4. A L0 lo stesso ticket produce la stessa PR dalle fixture.

*Nota 2026-09-15 (M5, ADR 0017):* la definizione del ruolo vive in `roles/<role>/prompt.md`, non in `roles/<role>/GEMINI.md`, perché Gemini CLI scopre i file di contesto nelle sottodirectory e caricherebbe tutte e sei le definizioni in memoria del worker; il prompt finisce in `~/.gemini/GEMINI.md` globale (decisione di plan §6). Gemini CLI v0.59.0 serve silenziosamente `gemini-3.5-flash` invece di `gemini-3.8-flash` senza alcun avviso; la fixture di ticket 0001 è registrata contro quello che veramente gira (ADR 0017 per i dettagli). Solo `dev-worker` ha prompt e budget reali a M5; gli altri cinque ruoli hanno solo `ROLE.md` che nomina quale milestone li eseguirà.

### M6 — Control plane
Dispatcher, macchina a stati del ticket, modello degli artefatti, idempotenza, audit log che ricostruisce la catena deploy → PR → task → spec.
**Fatto quando:** `./go e2e` percorre ticket → PR → CI → canary → verify fallito → rollback, senza intervento umano, e l'audit mostra la catena completa.

*Nota 2026-09-16 (M6, ADR 0019):* a L0 la "CI" del percorso e2e sono i sei gate di M4 eseguiti dalla tower sull'head della PR e pubblicati come commit status su Gitea, non un job di Gitea Actions: la socket del runner e il primo job di Gitea slittano a M8 (terzo rinvio, stesse tre condizioni di ADR 0015 §7; la regola di ADR 0003 vincola M8). Il canary rilasciato dopo la merge resta l'immagine stable sotto `0.2.0-waitlist`, non una build del merge commit (build e push su Zot a M8); ogni riga di audit lo dichiara. L'audit, per decisione mia, non legge solo il proprio archivio: confronta il documento con il code host e fallisce se divergono. `go-for-launch` e i primi prompt di `architect` e `test-reviewer` passano a M7.

### M7 — Agenti ADK
Product agent conversazionale, triage agent sugli alert, release agent che compone il promotion brief. Suite `adk eval` con casi che includono la domanda ambigua e l'alert fuorviante.
**Fatto quando:** `adk eval` passa in CI; un alert finto produce un incident con ipotesi ordinate e una proposta di rollback, senza che l'agente tocchi l'ambiente.

*Nota 2026-09-16 (M6, ADR 0019):* M7 eredita anche `go-for-launch` (lo stub `[launchpad] 100%: NOT YET (M7, go-for-launch)`; la regola di ADR 0003 vincola M7), i primi prompt reali di `architect` e `test-reviewer`, e la regola di perimetro del ticket 0003 prima del prossimo `record`.

*Nota 2026-09-16 (M7, ADR 0020):* i tre agenti ADK girano su ADK 2.9.1 dentro la workbench; a L0 il modello è replay di risposte registrate a L1 (fixtures/adk/), i tool e adk eval girano davvero, il modello no; `adk eval` giudica traiettorie di tool soltanto (nessun giudice LLM), ogni decisione è una tool call; `go-for-launch` landed (`./go promote`, provato da `./go demo-launch`, non una tappa di `./go demo`); a L0 il brief è renderizzato dal release record perché un record live non può essere replayato; i ruoli review (architect, test-reviewer, lo step `review` della tower), ticket 0003 e i due `record` di dev-worker vanno a M8.

### M8 — GCP (L2)
Terraform per progetto, Artifact Registry, Cloud Run, Cloud Deploy con le fasi canary e il verify job, Cloud Monitoring, Binary Authorization, Workload Identity Federation da GitHub, Secret Manager con credenziali per ruolo.
**Fatto quando:** su un progetto nuovo, `./go up PROFILE=l2` porta dallo zero al primo rollback automatico in meno di un'ora, e i file in `gates/` e `verify/` sono gli stessi di L0, verificato da un test che ne confronta gli hash.

*Emendamento 2026-09-20 (ADR 0022):* la firma delle immagini che M8 costruisce arriva **a ogni livello, prima a L0**: chiave locale generata a `./go up` (mai nel repo), firma pushata su Zot con l'immagine, verifica nel launchpad prima dello staging; una immagine non firmata è `NO-GO: launchpad — unsigned image`. Binary Authorization a L2 è il secondo adapter della stessa regola, non la prima volta che la regola esiste. *(ADR 0024)* Prima di scrivere `adapters/cloud-deploy/`, la suite di conformità Delivery (`gates/delivery-conformance.sh DELIVERY=<nome>`), passata da `envoy-canary`; `cloud-deploy` è chiuso quando la passa a L2, con `ci/vendor-free.sh` ancora verde. Cloud SQL è l'unico pezzo di L2 che non scala a zero: `infra/README.md` lo dichiara con il comando per fermare o cancellare l'istanza, e `./go down PROFILE=l2` ferma l'istanza. Il README riordinato come in §3 (locale prima, GCP dopo e dichiarato opzionale) fa parte di M8, perché è la milestone in cui la sezione GCP smette di essere un piano.

*Emendamento 2026-09-20 (ADR 0025, 0026, 0027, 0028), il livello meccanico di M8:*
- **L'artefatto di rilascio (ADR 0025).** Il primo job di Gitea Actions è la build: su push a `main`, con la socket del motore (tre condizioni di ADR 0015 §7, tutte e tre verificate nel testo dell'ADR), il job fa `./go publish TAG=sha-$GITHUB_SHA` — check-out con `git`, non con `actions/checkout`, per non mettere github.com nel percorso della demo L0. La porta `Registry` prende due verbi (`publish.sh`, `verify.sh`), `./go up` genera la chiave e pubblica l'immagine stable firmata, `core/steps/release.sh` aspetta lo status `image` sul merge sha (`await.sh`, `IMAGE_TIMEOUT=300` s) e passa `CANARY_TAG` al launchpad, che verifica la firma prima dello staging e deploya il digest verificato (`deploy.sh <version> <image>`). `CANARY_VERSION` non cambia significato. Il segnaposto `"stable image, not built from merge.sha (M8)"` sparisce da `core/launchpad.sh`, `core/steps/release.sh` e `README.md`: M8 non è chiusa finché la stringa esiste ancora in uno di questi tre file. Strumento: cosign 3.1.3, con `--tlog-upload=false` in firma e `--insecure-ignore-tlog=true` in verifica (senza questi due flag la firma passa da Rekor e la regola d'oro salta).
- **La suite di conformità (ADR 0026)** si scrive prima di `cloud-deploy`, con sei casi in ordine fisso, `CONFORMANCE=1` per non partire dentro `ci/contract.sh`, e il forzante del NO-GO che resta la regola di targeting committata (nessun interruttore di fault injection). Il freeze e il kill switch escono dal Makefile e passano dietro `adapters/$FLAGS/set.sh`, l'unico modo per far girare lo stesso caso a L2. *Emendamento 2026-09-20, decisione dell'owner:* un caso in più, a ogni livello, forza `NO-GO: launchpad — unsigned image` con un tag mai pubblicato — nessuno dei cinque casi originali toccava la firma.
- **L2 (ADR 0027)** è il percorso di rilascio, non quello del ticket: `artifact-registry`, `cloud-deploy`, `managed-prometheus` e flagd su Cloud Run completi; `ready.sh` per tutti gli altri adapter nominati in `profiles/l2.env`; i verbi di `pubsub`, `firestore`, `github` e `github-issues` vanno alla milestone che fa girare la tower su GCP (M10). **Il verify job di Cloud Deploy resta spento**: decide `verify/slo.sh`, a ogni livello — è l'emendamento a questa riga di piano che conta di più. Secret Manager tiene un segreto solo (la password del database); "credenziali per ruolo" diventa un service account per ruolo. Workload Identity Federation si crea qui e si usa la prima volta a M10. *Emendamento 2026-09-20, decisione dell'owner:* il rifiuto di Binary Authorization non si prova più a mano una volta — `gates/unsigned-refused.sh` (`./go unsigned-refused PROFILE=l2`, NO-GO a L0) lo esercita davvero, fuori da `core/` apposta, con un'immagine push­ata direttamente in Artifact Registry e mai firmata da `publish.sh`; entra nell'acceptance di M8 insieme al test degli hash.
- **La workbench si divide (ADR 0028):** gcloud e terraform (474 MB, misurati a chiusura M7) escono dall'immagine base e vanno in `workbench/cloud/Containerfile`, costruita `FROM` quella base; `WORKBENCH_FLAVOUR=cloud` nei profili l2/l3 e due righe in `./go` scelgono. cosign resta nella base, perché la firma serve prima a L0.

*Nota 2026-09-16 (M6, ADR 0019):* qui arrivano anche la socket del runner di Gitea e il primo job di Gitea Actions (tre condizioni di ADR 0015 §7), la build dell'immagine dal merge commit e il push su Zot. M8 eredita anche da ADR 0020 i ruoli review (architect, test-reviewer, lo step `review` della tower), ticket 0003 e i due `record` di dev-worker che risolvono il budget (entrambi richiedono una run PR a medio rischio a L1, lo stesso lavoro `record` del budget).

*Nota 2026-09-16 (chiusura M7, decisione mia):* i ruoli di review **non** entrano in M8: diventano una milestone propria, dopo M8, perché nessuna parte di quel lavoro dipende da GCP e in M8 ci starebbe solo per collocazione (secondo rinvio dei ruoli, terzo della socket). Numero proposto in HANDOFF: **M9 — Review**, prima del self-test notturno, che slitta a M10, e del design loop, che slitta a M11; da accettare o cambiare prima di iniziare M8. Dentro M8 invece va lo spostamento di gcloud e terraform (474 MB, nessuno script li usa prima di L2) dal workbench base a un'immagine `workbench-cloud`, con l'ADR che emenda 0004: è la milestone dove i due strumenti servono per la prima volta. Misure a chiusura M7: workbench 1.42 GB (gcloud 368, ADK 304, node 118, terraform 106); `./go demo` a freddo 684 s sui 900 di budget.

*Nota 2026-09-17 (decisione mia):* numero accettato senza cambi. M8 (GCP) resta aperto — la sessione dedicata a M8 non è stata chiusa — e questa sessione fa M9 prima, perché nessuna parte del suo lavoro dipende da GCP: rinumerazione applicata, il self-test notturno passa a M10 e il design loop a M11 in tutto il repo.

### M9 — Review
I ruoli `architect` e `test-reviewer` con prompt reali sul harness `gemini-cli` esistente (nessun agente ADK: sono ruoli che leggono il diff e commentano, non conversano né triano alert). Uno step `review` in `core/tower.sh` (precondizione `review`, prossimo stato `ci-passed` o `ci-failed`), inserito dove il risk scoring di M4 già chiede una seconda review (`policy/merge.env`, ADR 0016) e dove `core/steps/ci.sh` oggi si ferma con "nobody reviews until". La regola di perimetro del ticket 0003 (`gates/` o `record`, la scelta è dell'architect) prima del prossimo `record`. I due `record` di dev-worker che, sull'harness reale a L1, risolvono il budget di token (ADR 0020 §9's finding: 12M/call è troppo) e validano il prompt riscritto sotto il ticket 0004.
**Fatto quando:** una PR a rischio medio (fixture registrata a L1, rigiocata a L0) attraversa lo step `review`; `test-reviewer` la marca cambiata o approvata con un motivo tracciabile nel documento della tower; una fixture il cui diff esce dal perimetro del ticket non viene scritta da `record`, e il motivo nomina il file fuori perimetro (criterio letterale del ticket 0003).

*Nota 2026-09-17 (chiusura M9):* closed. Acceptance: `./go demo-review` at L0, `test-reviewer` approves medium-risk ticket 0005 (237 changed lines), `input_matches_recorded: true`; `./go ci` → `GO: ci`, 23 checks (three new: `perimeter`, `review`, `tower` updated); `./go demo` (warm) → `GO: demo, milestone M9, 270s to rollback (budget 900s, plan §2)`. Two dev-worker `record` runs: ticket 0001 (4 live attempts before passing mutation gate, 2,435,115 tokens, 32 tool calls, 328 s) and ticket 0005 (6 live attempts, 1,823,982 tokens, 34 tool calls, 249 s). TOKEN_BUDGET set to 2,600,000 (dev-worker); test-reviewer measured at 1,500,000 (from a 1,154,977-token run approving); architect measured at 600,000 (495,561-token run, not wired into tower per ADR 0021 §4). Two bugs found and fixed: (1) `core/steps/review.sh` BASE variable changed to use workspace's current HEAD instead of ticket's original base (caused `adapters/gemini-cli/run.sh`'s `git format-patch` to reproduce dev-worker's entire diff on replay; fixed by passing workspace HEAD as BASE, and `adapters/replay/run.sh` changed from `-f "$fixture/patch"` to `-s "$fixture/patch"` for defence in depth); (2) review step's input document header changed from literal `BASE_SHA..HEAD_SHA` to constant "Diff:" so replay's fresh commit hashes don't break input document hash matching. One pre-existing bug found, not fixed: `core/steps/release.sh:27`'s `[ "$(cat "$rc_file")" -eq 0 ]` intermittently reads an empty `$rc_file` and prints `Illegal number` to stderr (race between `tee`/subshell and `cat`; observed fallback state happens to be correct, so verdict is never wrong, but it's a real race condition). `.crew/.uv-cache/` accumulated ~194 MB from live runs and produced 21 gitleaks false positives (`generic-api-key` on sqlalchemy source strings like `ctx.api`, `.key`, purely from entropy heuristics); unrelated to repo secrets. M8 (GCP) remains open and deliberately not touched this session (no GCP dependency in M9).

### M10 — Piattaforma (L3) e self-test notturno
Agent Engine per gli agenti ADK, BigQuery agent analytics, adapter Cloud Workflows, opzione GKE, e un job schedulato che ogni notte esegue il golden path completo su un progetto usa e getta.
**Fatto quando:** il badge del nightly è verde nel README, e una regressione nei prompt lo fa diventare rosso.

*Nota 2026-09-20 (ADR 0027 §1, ADR 0025 §4):* M10 eredita da M8 i verbi L2 della tower (`pubsub`, `firestore`, `github`, `github-issues`), il job dei gate su `pull_request` (ADR 0019 §4's "option A") e il primo consumatore reale di Workload Identity Federation: è la milestone in cui la tower gira davvero su GCP, quindi è lì che quel codice smette di essere infrastruttura senza consumatore.

### M11 — Console, design loop e materiale da palco
*Emendamento 2026-09-20 (ADR 0023): la console assorbe il design loop.* La console è la superficie umana della piattaforma e il soggetto che si progetta con Stitch: il server MCP di Stitch collegato all'agente interattivo produce gli artefatti in `design/`, committati, da cui il frontend worker costruisce la console senza mai chiamare Stitch.

Principi vincolanti (ADR 0023):
- **Una vista, non una fonte di verità.** Legge da git (ticket, ADR, commit, PR via `CodeHost`) e dallo state store (documenti della tower). Non ha un database suo, non duplica nulla, non tiene stato che non si ricostruisce da zero.
- **Due sole azioni in scrittura:** rispondere a una domanda aperta su un ticket (la stessa che il ruolo product pone con `ask_product_owner`) e premere go-for-launch (lo stesso `core/promote.sh` di `./go promote`). Nient'altro accetta input.
- **La CLI resta il canale primario.** Ogni cosa che la console mostra o fa esiste già come comando `./go`; senza console non si perde nulla.
- **I grafici non si riscrivono.** La console incorpora o linka i pannelli della porta `Charts` (§4): Grafana a L0/L1, Cloud Monitoring a L2/L3.

Schermate: lavagna dei ticket sulla macchina a stati della tower; dettaglio ticket con criteri di accettazione e domande aperte; navigatore ADR con le relazioni di emendamento (chi emenda chi, letto dalle righe `Status`); catena di audit navigabile da produzione fino alla spec (lo stesso `./go audit`); pannello go-for-launch con promotion brief ed esito canary.

Con la console: `docs/TALK.md` con la sequenza della demo e i video di backup di ogni passaggio.

**Fatto quando:** a L0, senza account e senza chiave, la console si apre, mostra il ticket 0001 con la sua catena completa (spec → ticket → PR → CI → merge → release → verify → rollback), e il go-for-launch premuto dalla console porta davvero il canary al 100% (lo stesso effetto di `./go promote` con `GO`). Un cloner senza accesso a Stitch ottiene comunque la console corretta dagli artefatti nel repo.

*Nota 2026-09-23 (ADR 0029, risequenziamento):* M12 è la prossima milestone. M11 viene anticipata subito dopo l'esperimento sul repo legacy (§14), perché il cliente di un engagement vuole vedere la catena di audit e premere lui go-for-launch. Il track cloud di M8 e M10 aspettano chi li paga — la politica che §11 già applica al secondo adapter cloud vale anche per il primo. Nulla di loro viene cancellato.

*Emendamento 2026-11-04 (ADR 0047, proposta; progetto in [docs/plans/console.md](plans/console.md)):* la console è per il cliente business con una sola istanza, ed è un componente nuovo, `console/`, accanto alla board che resta l'explainer in sola lettura. Legge **un solo documento versionato, il logbook** (`lights-out/logbook/1.0`), che `./go logbook` (`core/logbook.sh`) assembla dai documenti della tower, da un log dei rilasci, dai post mortem di M22 e dai file di policy; è l'unico punto che cambia quando M19, M21 o M22 cambiano una forma. **Una sola scrittura**, go-for-launch attraverso `core/promote.sh`, che registra chi ha premuto e da dove; cade la risposta alla domanda del ruolo product (ADR 0023 §2(a)). Cade anche la porta `Charts` con il container Grafana: nessuna schermata disegna serie temporali. Le cinque schermate diventano: i ticket della settimana con GO/NO-GO e il perché; la catena di un ticket dal ticket al rollback; incidenti e post mortem con i ticket di fix; go-for-launch con il brief e un bottone; le soglie con la provenienza. A L0 senza chiave: LIVE con il piano su (`./go console`, loopback) oppure uno snapshot committato prodotto da un `./go demo` vero; il bottone, quando non c'è niente da promuovere, è disabilitato e dice perché. Fuori da loopback la console non parte senza `CONSOLE_AUTH` dichiarato: identità da un proxy fidato (IAP, oauth2-proxy) e una lista di chi può premere. Il "Fatto quando" sopra resta, con la pressione via HTTP provata da `./go demo-console`, fuori da `./go demo`. **Si costruisce dopo il merge di M22**, con due precondizioni: il documento della tower copia da `run.json` provider, modello servito, token e durata (la metà di costo di ADR 0031 §3), ed esiste un log append-only dei rilasci, `.crew/releases.jsonl`. Portfolio fra clienti, report di valore e proposta restano fuori (§14): il progetto privato legge solo il logbook.

*Stato 2026-11-04 (prima versione, su branch, non mergiata; decisioni provvisorie da confermare):* l'ADR è rinumerata **0047** (la 0046 è quella dell'egress degli harness su un altro branch). L'owner dormiva: per ognuna delle dieci decisioni aperte in fondo ad ADR 0047 la sessione ha preso la raccomandazione dell'ADR e l'ha scritta come "Provisional decision (2026-11-04, owner to confirm)", con l'alternativa accanto; altre otto decisioni prese costruendo sono nella stessa lista (11–18), e le regole fissate costruendo sono in fondo a [docs/plans/console.md](plans/console.md), "Decided at build". Costruito: `core/logbook.sh` + `core/logbook.py` e lo schema `core/logbook/1.0.schema.json`; P1 (i campi di costo di `run.json` nel documento della tower, in assign, rework e review) e P2 (`.crew/releases.jsonl`, scritto da launchpad e da promote); `core/promote.sh` registra chi ha risposto e da dove (`by`, `via`, `rejected` su NO-GO) e risponde sul brief già mostrato (`GO_FOR_LAUNCH_BRIEF_SHA256`); `console/` (server stdlib e pagina statica come la board, cinque schermate, LIVE e snapshot, `CONSOLE_AUTH` loopback/proxy/public, un solo POST); `./go logbook`, `./go console`, `./go demo-console`; `ci/logbook.sh` scritto dal gate-writer dall'ADR e dal piano. `./go demo-console` gira come passo del job `launch`, fuori da `./go demo`, che non cambia. Non ancora: il mirror dell'emulatore (ADR 0031 §6, decisione 3), il design con Stitch e il frontend worker (decisione 6: questa prima versione l'ha scritta la sessione), la verifica dell'asserzione firmata di IAP (decisione 8). Le prove su Actions e la lista delle decisioni da confermare sono in `.claude/context/HANDOFF.md`.

### M12 — Il seam: l'app dietro una porta
L'app bersaglio smette di essere cablata nella piattaforma. Una porta per il workload (nome e contratto in ADR 0030) con un file d'istanza che dichiara tutto ciò che gate, launchpad, verify e tower devono sapere dell'app: path del package, lockfile, comando di test, target di mutation, endpoint delle metriche, flag del kill switch, servizi compose. `ci/app-free.sh` fallisce se `core/`, `gates/`, `verify/` o `adapters/` nominano l'app, come `ci/vendor-free.sh` fa per i fornitori di Delivery. Un secondo workload, deliberatamente minimo, dimostra che il seam è reale e non solo dichiarato. Zero ruoli nuovi, zero modelli nuovi, nessuna capacità visibile in più: è la milestone che rende possibili tutte le altre.
**Fatto quando:** `./go ci` è verde con il nuovo check `app-free`; `./go demo` a L0 stampa lo stesso `GO: demo` di M9, entro lo stesso budget di 900 s, con le stesse fixture e gli stessi ticket; e il secondo workload arriva al rollback automatico e passa i gate su una fixture committata, con un comando fuori dalla lista fissa di `./go demo` (ADR 0003), la cui forma è fissata in ADR 0030.

*Nota 2026-09-23 (chiusura M12):* closed. Acceptance, all on a rebuilt workbench (`./go clean`) and a clean plane: `./go demo` → `GO: demo, milestone M9, 525s to rollback (budget 900s, plan §2)`, 26 ci checks GO including `workloads` and `app-free`, rollback on `error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=0.000`; `./go demo-seam` → `GO: demo-seam`, rollback on `error_rate canary(0.2.0-outage)=1.000 stable(0.1.0-minimal)=0.000`, its own `honest-fix` fixture GO; `docker-compose config` of the merged app project byte-identical to the pre-M12 capture. The live runs happened on `APP_PORT=9000`: on the dev machine host port 8080 was held by another project's container, so the edge's host port became a knob (Makefile and compose, default 8080, `.env.example` and README say so) instead of stopping it — the likeliest way `./go demo` fails for a cloner, now with a one-line fix. The `.env` parking pre-step was wrong: gitleaks' working-tree scan ignores `.gitignore`, so the key must leave the repo directory, not be renamed inside it. What M12 left unproven, and the §14 experiment needs first: a workload in its own repository (`adapters/gitea/bootstrap.sh` pushes this checkout), a worker toolchain beyond Python and Node, a workload-neutral dev-worker prompt, and an envoy-canary probe without `python3`.

### M13 — Attach: lights-out su un repository suo
*Riscritta 2026-11-03, decisione dell'owner (ADR 0037).* L'obiettivo di prodotto fissato il 3 novembre è: cloni lights-out, lo attacchi al tuo repo (qualunque stack, prima o poi), vedi tutto su una dashboard. La sequenza concordata è M13 attach, M14 stack, M15 loop di rework, M16 rete di agenti, M17 dashboard. Questa milestone è la prima: chi tiene un clone pulito di lights-out lo punta su un repository git separato, suo, e ottiene gli stessi gate, lo stesso canary e lo stesso rollback, senza forkare lights-out. Tre cose, la più piccola che passa i criteri:
- **Indipendenza dal repo.** `./go attach <path>` clona il repository dell'utente in `.attached/` (gitignorata, dentro il checkout: è l'unico posto che il workbench e i bind mount di compose vedono a ogni livello, e lights-out non scrive mai nel repo dell'utente); `./go detach` la toglie. Finché c'è, è il workload di default. Gitea fa da mirror del repository attaccato invece che di lights-out, i gate fanno `git -C "$WORKLOAD"` sul suo repository, e il contratto si legge solo da lì. Le modifiche mergiate tornano all'utente con un `git fetch` da Gitea, dichiarato (Gitea è il code host fino all'adapter GitHub, M10).
- **`.lights-out/` nel repo bersaglio.** Ciò che un workload deve oggi (le sette chiavi di `workload.env`, il frammento compose, `flags/flags.json`, `smoke.sh`, `load.sh`, `fixtures/gates/`) più un `worker.md`, il brief che sostituisce il testo dell'app cablato in `roles/dev-worker/prompt.md` (la parte `worker.md` dell'ADR 0031, l'unica presa), e `tickets/`. I runner dei gate restano dove la porta dice, nell'immagine di test. `app/` resta com'è; `workloads/minimal/` diventa un repo attaccabile, con il contratto in `.lights-out/`.
- **Soglie in un file, per repo: `.lights-out/policy.env`.** Sovrascrive i default della piattaforma oggi sparsi (`policy/merge.env`, `verify/slo.sh`, `MUTATION_BASELINE` di `workload.env`), che si raccolgono in `policy/merge.env`; i path a rischio alto dell'app passano in `app/policy.env`. Invarianti: una PR è giudicata dalla policy della base, mai dalla sua (ticket 0007); `.lights-out/*` è rischio di piattaforma e non si auto-mergia mai; una chiave sconosciuta o un valore malformato è un NO-GO che nomina la chiave; ogni riga di override porta un commento di provenienza (misura, vincolo esterno, decisione); un override più lasco del default si riporta su stderr (la dashboard lo mostra in M17).

Fuori: il worker sulla toolchain del bersaglio e gli stack non Python (M14), il loop di rework (M15), la rete di agenti (M16), la dashboard (M17).
**Fatto quando:** `./go ci` verde, con un check `ci/attach.sh` che prova che la piattaforma legge solo il contratto `.lights-out/` del bersaglio, le invarianti della policy e che a L0 un run della crew su un repo attaccato fallisce con un messaggio che chiede L1 e una chiave Gemini, mai un finto successo; `ci/app-free.sh` vieta a `core/`, `gates/`, `verify/` e `adapters/` di nominare il repo attaccato; `./go demo-seam` copia `workloads/minimal` in un repository git nuovo fuori dall'albero di lights-out, lo attacca, e `up`, `smoke`, `verify`, `demo-rollback` e `demo-gates` sono tutti GO su di esso; `./go demo` arriva ancora al rollback automatico a L0, senza chiave, entro i 900 s, con i secondi misurati nella nota di chiusura.

*Nota 2026-11-03 (ADR 0037):* questa M13 sostituisce la "M13 — Pronti per l'esperimento: prompt neutro e report" aggiunta il 2026-09-23, il cui testo resta qui sotto per traccia. Del vecchio testo M13 prende solo il prompt neutro (il `worker.md`), senza ri-registrare le fixture 0001 e 0005: la ri-registrazione chiede la chiave e un run L1 dell'owner, ed è una decisione aperta. `./go report` e i documenti della tower che sopravvivono a `./go down` (ADR 0031 §3–§6, ancora proposto) non sono in M13: la proposta è M17, perché la dashboard legge gli stessi dati; da confermare.

*Nota 2026-11-03 (fine sessione M13, branch `claude/m13-attach-c88b96`, da rivedere e mergiare):* acceptance run for real from a full clone of the branch (a git worktree cannot drive git inside the workbench, see HANDOFF), warm images, a host shared with another session's plane runs: `./go ci` → `GO: ci`, 23 checks with the new `attach`; `./go demo-seam` → `GO: demo-seam` in 149 s, `workloads/minimal` as a fresh repository outside the tree, attached, rollback on `error_rate canary(0.2.0-outage)=1.000 stable(0.1.0-minimal)=0.000`, `honest-fix` GO; `./go demo` → `GO: demo, milestone M9, 765s to rollback (budget 900s, plan §2)`; `./go demo-gates` on the app's six fixtures GO, the migration fixture high risk through `app/policy.env`. At L0 `./go assign` on an attached repository answers `NO-GO: crew` naming L1 and `GEMINI_API_KEY`. Open for the owner: re-recording fixtures 0001/0005 on the neutral prompt; report and persistence to M17; the release of an attached repository's merge (no `image` job for it) to M14. Numbering: ADR 0037, because 0036 is taken by the unmerged `agentic-network` branch.

#### M13 (testo del 2026-09-23, sostituito) — Pronti per l'esperimento: prompt neutro e report
*Aggiunta 2026-09-23, decisione dell'owner.* La milestone piccola in main che l'esperimento del §14 presuppone. Tre cose, nessuna capacità dell'harness cambia:
- **Il prompt del dev-worker diventa neutro rispetto al workload.** `roles/dev-worker/prompt.md` oggi fissa `app/backend/`, `uv sync` e `pytest` (righe 15–31); ciò che è specifico dell'app (dove sta il codice, come si lanciano i test) passa in un file del workload che il worker legge. Le fixture 0001 e 0005 si ri-registrano a L1 sul prompt nuovo, così L0 continua a replayare ciò che L1 ha prodotto. `ci/app-free.sh` estende il suo scope a `roles/`.
- **`./go report`**: il resoconto di un lotto di ticket, generato dai dati che la piattaforma ha già (documenti della tower, verdetti dei gate, `run.json` del harness, release record, `./go audit`), senza stato proprio (la regola della console, ADR 0023). Per ticket: esito, PR, perimetro, verdetto di ogni gate con mutation score contro il baseline, review con motivo, tentativi/token/tool call/durata, canary. In testa: il criterio di uscita, il costo totale e per ticket, i fallimenti per causa. Markdown; HTML se serve da mostrare. È il deliverable di ogni engagement, non solo il case study: per la regola di confine sta qui.
- **I documenti della tower sopravvivono a un `./go down`.** Oggi stanno nell'emulatore Firestore senza volume; un esperimento che dura giorni li perderebbe. Il come (volume, export prima del `down`) è dell'ADR.
Prima di scrivere: un ADR corto per il report e la persistenza.
**Fatto quando:** `./go ci` verde con `app-free` esteso a `roles/`; `./go demo` identico entro il budget, con le fixture 0001/0005 ri-registrate (`input_matches_recorded: true`); `./go report` su `./go e2e` produce il resoconto del ticket 0001 con numeri che coincidono con quelli di `./go audit`; e dopo `./go down` + `./go up` il report si rigenera identico.

### M15 — Il loop di rework
*Aggiunta 2026-11-03, decisione dell'owner (sequenza M13 attach, M14 stack, M15 rework, M16 rete di agenti, M17 dashboard; le sezioni M13 e M14 arrivano con le loro sessioni).* Oggi un NO-GO prima del merge chiude il ticket: un gate in NO-GO porta la tower in `ci-failed`, terminale; una review che non approva è un verdetto, mai un giro di modifiche. M15 aggiunge due dei cinque loop: il **loop di condizione** (l'uscita la giudica qualcuno che non è chi ha fatto il lavoro: i gate) e il **loop di review** (review → si risponde a ogni rilievo → si ripusha). Tutti e due governati dall'harness, tutti e due solo prima del merge. Dopo il merge non cambia niente: un canary che fallisce torna indietro da solo, e il GO/NO-GO umano prima del 100% resta l'unico gate umano.
- Dopo un NO-GO di un gate o una review con CHANGES-REQUESTED, il dev-worker riparte sullo stesso ticket, con lo stesso perimetro, dalla propria PR, e riceve come input il verdetto precedente: la riga NO-GO più i dettagli del gate (per esempio i mutanti sopravvissuti), oppure i rilievi del reviewer. Mai la conversazione sua o dei reviewer; i reviewer continuano a leggere solo ticket e diff.
- Nessun settimo ruolo: il rework è uno step della tower, non un ruolo (`ci/roles.sh`).
- Tentativi limitati da un numero con provenienza, scritto nell'ADR. Al limite il ticket finisce in uno stato che dice chiaramente che serve una persona. Mai un loop silenzioso.
- Stesse regole a ogni tentativo: policy e gate della base (ticket 0007), stesso controllo di perimetro, stesso risk routing. Un tentativo che allenta un test o un gate lo prendono la mutation e i path di rischio di piattaforma, non la fiducia.
- Ogni tentativo resta nella storia della tower (verdetto, numero del tentativo, timestamp); la board lo mostra, con la tabella `tower-machine` allineata e uno scenario "NO-GO, rework, GO".
- A L0 le risposte dei tentativi 1 e 2 possono essere fixture scritte a mano, dichiarate come tali nel README; gate, tower e loop sono veri. Nessun token Gemini senza chiedere.
Prima di scrivere: ADR 0038.
**Fatto quando:** `./go demo-rework` a L0, senza chiave, stampa `GO: demo-rework`: un ticket va in NO-GO al tentativo 1, torna al worker con il verdetto, passa in GO al tentativo 2 e viene mergiato, con la catena di `./go audit` verde; `./go ci-tower` dimostra che un ticket che non passa mai si ferma al limite in `needs-human`; `./go ci` è verde; `./go demo` arriva ancora al rollback automatico del canary a L0, senza API key, entro 900 s (secondi misurati nel report).

*Nota 2026-11-03 (stato M15, branch `m15-rework`, non mergiato):* `./go demo-rework` → `GO: demo-rework` in 404 s su un piano freddo: tentativo 1 `NO-GO: gates — mutation: … 4/8 mutants on changed lines killed (0.500 < 0.666)`, il worker riceve la riga e i quattro sopravvissuti (`meetups/geocoder_client.py:26 …`), tentativo 2 `GO: gates — risk low, auto-merge`, merge, rollback del canary, `GO: audit` con la traccia del rework. `./go ci` → `GO: ci` (`ci-tower` con i casi del loop e del limite, `ci-contract` con `NOGO_DETAILS`, `ci-board`). **Regola d'oro, primi tentativi:** sulla macchina di sviluppo, con load average dell'host fra 9 e 135, `./go demo` è andato in NO-GO tre volte su questo branch (smoke a 3 s di timeout; due volte l'attesa di 300 s dell'immagine del merge commit in `e2e`, 1111 s e 1979 s) e una volta su `main` 1c62d1d nelle stesse condizioni (staging non healthy in `demo-rollback`, 810 s). Rifatto più tardi lo stesso giorno, con il piano libero e load average 5: `./go demo` → `GO: demo, milestone M9, 712s to rollback (budget 900s, plan §2)` da un clone pulito di `m15-rework` (da61847), senza chiave. Regola d'oro verificata. Trovato: il runner Gitea esegue il job `ci` di `.github/workflows/ci.yml` (`./go ci`) a ogni push dentro il piano L0, in coda davanti al job `image` che `e2e` aspetta per 300 s; e `./go` non funziona da un git worktree (il `.git` del worktree sta fuori dal mount). Il limite di quattro tentativi per ticket (`policy/rework.env`) è confermato dal proprietario il 2026-11-03.


*Emendamento 2026-11-03:* le milestone da M18 a M24 — modello a scelta, harness `claude-code` e `codex`, i gate senza piano, GitHub come code host, il post mortem, il pacchetto, l'esperimento con tre fornitori — sono in §16, con M14 assorbita da M20 e M21.
---

## 8. Il golden path

Un unico test end-to-end, che è insieme la demo, il test di regressione della piattaforma e l'eval degli agenti. Gira a ogni livello.

1. Arriva un ticket: "aggiungi la lista d'attesa quando il meetup è pieno".
2. Il product agent verifica i criteri di accettazione e apre una domanda se mancano.
3. Il dev worker implementa nel suo worktree e apre una PR.
4. La CI esegue i gate, il risk scoring dice rischio medio, parte la review agent.
5. Merge, build, immagine firmata e firma verificata (a ogni livello, ADR 0022), Cloud Deploy o Envoy porta al 5%.
6. Il verify legge le metriche e boccia, perché la feature dietro flag restituisce 5xx quando il flag è acceso.
7. Rollback automatico, incident aperto, ipotesi ordinate.
8. Seconda corsa con il flag spento: passa, arriva al gate umano, promozione al 100% — da `./go promote` o dal pannello della console, stesso codice.
9. Accendi il flag in produzione, gli errori salgono, spegni il flag: risolto in secondi, senza deploy.

Il punto 6 e il punto 9 sono due leve diverse con due tempi diversi, ed è la cosa che il pubblico deve portarsi a casa.

---

## 9. Regole per Claude Code

- **Verifica prima di scrivere.** Antigravity, Stitch, Gemini CLI, ADK e Cloud Deploy si muovono in fretta. Prima di usare un'API, leggila nella documentazione ufficiale corrente. Se una cosa non esiste più come descritta qui, fermati e segnalalo invece di adattare il piano in silenzio.
- **Pinna tutto.** Versioni esatte per ADK, Gemini CLI, immagini base, provider Terraform. Rinnovi solo con un commit dedicato che fa passare gli eval.
- **Niente mock silenziosi.** Se qualcosa non è implementabile a un livello, il README lo dichiara e il codice fallisce con un messaggio chiaro. Mai una finta implementazione che sembra funzionare.
- **Ogni milestone lascia il repo eseguibile.** Prima di chiudere una milestone: `./go demo` verde su una macchina pulita.
- **Nessun segreto nel repo.** Nemmeno negli esempi. `.env.example` con valori finti e un check in CI.
- **Test scritti dalla spec.** Anche i test del repo stesso. Se un test è stato scritto guardando l'implementazione, il mutation score lo smaschera.
- **ADR per ogni scelta strutturale**, in `docs/adr/`, corti, con le alternative scartate e il motivo.
- **Commit piccoli** con riferimento alla milestone.
- **README verificato su macchina pulita**, container senza cache, prima di ogni release. È la promessa principale del progetto.
- **Toolchain nel container.** Sull'host solo podman, git e una shell POSIX. Tutto il resto vive in `workbench/`. Podman rootless è il motore di riferimento, docker supportato ma non documentato. ADR 0004.
- **Header SPDX** `SPDX-License-Identifier: Apache-2.0` solo nei file di ingresso di ogni componente (entrypoint, Makefile, Containerfile, `main`), non ovunque.

## 10. Da verificare prima di iniziare

Elenco delle cose che possono essere cambiate e vanno confermate sulla documentazione ufficiale al giorno uno:

1. Autenticazione di Gemini CLI per chi clona: quale percorso è attivo oggi, con quali quote, e qual è l'ID modello corrente della linea Flash (i rilasci sono usciti a ritmo di uno ogni poche settimane).
2. Antigravity SDK: superficie Python, licenza, limiti del piano gratuito, stato della CLI su Linux.
3. Stitch: esiste ancora il server MCP, quali sono i tetti mensili, quali target di export.
4. ADK: versione stabile corrente e compatibilità dell'adapter Claude/Vertex se ti servirà il confronto tra repo.
5. Cloud Deploy: supporto canary per Cloud Run e forma attuale del verify job e delle automazioni di promote.
6. Emulatori Pub/Sub e Firestore: copertura delle API che usiamo.
7. Gitea Actions: quali feature di GitHub Actions non supporta, così isoliamo gli step.

*Verificato 2026-09-20, prima di scrivere M8 (ADR 0025, 0027).* Punto 5: il canary di Cloud Deploy per Cloud Run **esiste ancora** e vale per servizi e worker pool, non per i job; `customCanaryDeployment.phaseConfigs` prende fasi con percentuale e `verify` opzionale, la fase `stable` al 100% è implicita, si avanza con `gcloud deploy rollouts advance` o con una automation; **le fasi canary sono saltate al primo deploy su un target**, quindi `./go up PROFILE=l2` deve creare il servizio prima; serve comunque uno `skaffold.yaml` anche per Cloud Run. Due derive rispetto a quello che il piano dava per scontato: (a) **Binary Authorization** — il controllo *sigstore* è solo continuous validation, su GKE e Artifact Registry, mentre l'ammissione su Cloud Run vuole attestor e attestazioni con chiave PKIX/KMS: la verifica della firma che decide resta quella del launchpad (cosign, stessa riga a ogni livello), BinAuthz è la seconda serratura (ADR 0027 §5); (b) **cosign** è alla 3.1.3, dove il formato bundle e i referrers OCI 1.1 sono il default e una firma con chiave locale finisce su Rekor se non si passa `--tlog-upload=false` (e `--insecure-ignore-tlog=true` in verifica) — senza quei due flag la firma a L0 richiederebbe rete e un log pubblico. Terzo dato: `google-github-actions/auth` è alla v3.

## 11. Rischi noti

| Rischio | Cosa succede | Mitigazione |
|---|---|---|
| Quota gratuita insufficiente a L1 | il cloner prova, sbatte sui rate limit, molla | task del demo piccoli, L0 come default assoluto, messaggio d'errore che spiega la quota |
| Antigravity o Stitch cambiano | la demo si rompe una settimana prima del talk | entrambi fuori dal percorso critico, artefatti committati, video di backup |
| L0 e L2 divergono | il repo pubblico diventa demo-ware | test che confronta gli hash di `gates/` e `verify/` tra i profili, nightly su L2 |
| Costo di L2: ogni run da M8, più il nightly da M10 | fattura a sorpresa | progetto usa e getta, scale to zero, Flash sui ruoli non critici; il budget alert è una **risorsa Terraform** (`google_billing_budget` in `infra/project.tf`, ADR 0027 §2) creata dal **primo** `terraform apply` di M8, non un'aggiunta di M10 — importo e soglie sono una decisione dell'operatore, e un budget avvisa, non blocca la spesa |
| Il repo diventa enorme | nessuno lo legge | l'app bersaglio resta piccola, se cresce si taglia |
| docker è uno shim di podman | ci-engine-compat passa senza aver testato docker | il gate stampa le due versioni separate e marca lo shim come non testato |
| Cloud SQL resta acceso | costo fisso fra un test e l'altro, l'unico in L2 | dichiarato in §3 e in `infra/README.md`; `./go down PROFILE=l2` ferma l'istanza; il budget alert della riga sopra, attivo dal primo apply |
| Un adapter cloud in più | un nightly in più, un progetto GCP (o altro) che costa, una superficie che si rompe quando il fornitore cambia API | **politica: un solo adapter cloud alla volta** (`cloud-deploy`); il secondo si scrive quando qualcuno lo paga, e paga anche il suo nightly. Candidato naturale per il terzo adapter Delivery, quando servirà: Kubernetes con Argo Rollouts — legge già PromQL e copre più clienti di un adapter legato a un singolo fornitore (ADR 0024) |
| La console diventa una seconda fonte di verità | CLI e console divergono, la demo mente | nessun database della console, due sole scritture che chiamano il codice della CLI (ADR 0023) |
| Il job di Gitea Actions entra nel percorso della demo | `./go demo` diventa rosso per un runner ballerino, non per il canary | il fallimento è preciso (status del commit, non timeout) e `demo-rollback`, la prova del solo controller, non passa dal runner (ADR 0025) |
| Le percentuali del canary vivono in due posti | `core/launchpad.sh` e la pipeline di Cloud Deploy divergono e nessuno se ne accorge | `shift.sh` boccia rumorosamente una percentuale senza fase, nominando il file della pipeline (ADR 0027 §3) |
| Il seam è dichiarato, non provato | un secondo workload scopre che i gate sanno ancora dove sta l'app | `ci/app-free.sh` più il secondo workload minimo nell'acceptance di M12 (ADR 0029) |
| Il mutation tool del linguaggio del legacy è debole o assente | il gate più affilato dell'harness si riduce a perimetro, risk scoring e audit | il repo dell'esperimento si sceglie in un ecosistema con un mutation tool serio — Java/PIT, .NET o JavaScript/Stryker — prima di promettere qualcosa a un cliente (ADR 0029 §6) |
| Il progetto-fabbrica entra in B dalla porta di servizio | un hook privato che solo il consumatore usa, e B diventa un fork mantenuto in due posti | la regola di confine di §14: se il consumatore ha bisogno di un hook, l'hook entra qui, aperto, come porta (ADR 0029 §3) |

## 12. Cosa non fare

- Non mettere ADK nel percorso di chi scrive codice sul repo: serve un harness con file, shell e git, non un orchestratore di conversazioni.
- Non usare un albero di agenti come control plane di un flusso che dura giorni.
- Non dare credenziali di produzione a un agente, a nessun livello, nemmeno a L0 per comodità.
- Non lasciare che il verify del canary dipenda da un giudizio del modello: la decisione è numerica, il modello arriva dopo per spiegare.
- Non aggiungere un settimo ruolo senza togliere qualcosa: sei ruoli è un vincolo di scope voluto, e ogni ruolo in più è un altro confine di fiducia da governare. Il numero scritto nel README e nei prompt deve coincidere con `roles/`, e `ci/roles.sh` lo verifica (2026-11-02).
- Non dare alla console una scrittura che la CLI non ha, e non farle tenere stato suo: è una vista.
- Non scrivere un secondo adapter cloud finché il primo non ha un nightly verde e qualcuno che paga il secondo.
- Non nominare un fornitore di Delivery in `core/`, nemmeno in un commento: `ci/vendor-free.sh` lo boccia.
- Non mettere una capacità solo a L2. Se il cloud sa fare una cosa che il locale non sa, il locale è una demo, e la regola d'oro salta.
- Non lasciare che sia il verify di un fornitore a decidere il canary: decide `verify/slo.sh` con `verify/slo.promql`, a ogni livello (ADR 0027 §3).
- Non nominare l'app in `core/`, `gates/`, `verify/` o `adapters/`: da M12 `ci/app-free.sh` lo boccia (ADR 0029, ADR 0030 §5).
- Non far entrare in questo repo ciò che serve solo a chi gestisce molti engagement (intervista, PoC, proposta, portfolio): è il progetto consumatore, e consuma solo interfacce pubbliche (ADR 0029 §3).
- Non promettere l'harness su un linguaggio il cui mutation tool non è stato provato sull'esperimento (§14).

---

## 13. Prompt di partenza per Claude Code

> Leggi `docs/PLAN.md` e `CLAUDE.md`. Prima di scrivere codice verifica sulla documentazione ufficiale i sette punti della sezione 10 e riportami solo ciò che risulta diverso dal piano. Poi fermati e aspetta.

Da lì in avanti una milestone per sessione, con `/milestone M0`, `/milestone M1` e così via. Fra una milestone e l'altra: checkpoint del contesto, `/clear`, sessione nuova.

---

## 14. Il secondo arco: l'harness su un repo legacy

*Aggiunto 2026-09-23 (ADR 0029).* Il 22 settembre la domanda era se la piattaforma potesse partire dall'intervista con un cliente e consegnare una PoC; poi se dovesse diventare un'intera azienda tech agentica. La risposta, dopo aver misurato il repo, è stata no a entrambe come prossimo passo — e sì a una cosa più piccola e più rara.

### Le tre direzioni pesate

| | A · Fabbrica end-to-end | B · Harness su repo legacy | C · Chiudere il piano |
|---|---|---|---|
| Chi paga, quanto gli fa male | medio — agenzie; il dolore è la velocità del pre-sale | **alto** — enterprise con legacy, budget già stanziati, paura acuta | basso diretto; credibilità |
| Differenziazione | bassa davanti (chat→spec→scaffold lo fanno tutti); alta solo grazie a B dietro | **alta** — gate numerici, perimetro, rollback, audit | media |
| Distanza da oggi | 2 milestone strutturali + 3 di ruoli + un loop di affinamento senza design | 1 strutturale + 1 gate pack + un baseline | 0 strutturali; M8 cloud costa denaro |
| Rischio regola d'oro | **alto** — intervista e affinamento sono human-in-the-loop; a L0 resta un engagement finto replayato | basso — il seam si prova con `./go demo` identico | nullo |
| Fragilità al modello | **alta** | bassa — il valore è nell'harness, il modello è dietro una porta | bassa |
| Verificabilità prima di investire | bassa | **alta** — una milestone e un repo vero | n/a |

Due righe decidono. La fragilità al modello: tutto quello che il repo ha già subito (routing 3.5/3.8 silenzioso, pin della CLI, budget rimisurati tre volte) colpisce dieci volte più forte su intervista, PoC e affinamento che su un gate di mutation. E A contiene B: la metà dietro della fabbrica *è* l'harness, senza la quale la metà davanti è un me-too. B è il test più economico della parte portante di A.

### La decisione

Direzione B, open. Apache 2.0 invariata: l'harness è l'artefatto di fiducia, un CTO lascia agenti autonomi sul suo monolite solo perché può leggere i gate. I ricavi vengono dal lavoro consegnato con l'harness — engagement di modernizzazione — non dalla licenza. La fabbrica (A) diventa un progetto separato, privato, che consuma lights-out solo attraverso interfacce pubbliche, e parte solo dopo che lights-out ha un consumatore diverso dal suo autore.

*Emendamento 2026-11-02, decisione dell'owner (ADR 0029, "Amendment 2026-11-02"):* l'ordine degli obiettivi è **visibilità** (talk, stelle su GitHub), poi **un'azienda** se arriva un co-founder o un finanziatore, poi **ricavi**. Il repo resta gratuito, Apache 2.0, senza tier a pagamento; i ricavi sono indiretti (talk, formazione, engagement che arrivano da soli). Un engagement è un design partner, non un passo della sequenza. I contributi entrano con il DCO (`Signed-off-by:`), senza CLA. Tempo disponibile: 5–15 ore a settimana.

**Regola di confine.** "Un cliente con una sola istanza ne ha bisogno?" → lights-out. "Ha senso solo per chi gestisce molti engagement?" → il progetto consumatore. Sei ruoli, ops continuo, console per istanza → qui. Intervista, PoC, proposta, portfolio → là. Se il consumatore ha bisogno di un hook che qui manca, l'hook entra qui, aperto, come porta.

### La sequenza

1. **M12 — il seam** (§7). Nessun rimpianto in qualunque scenario.
   **M13 — prompt neutro e report** (§7), subito dopo: l'esperimento non parte senza.
   *Emendamento 2026-11-03, decisione dell'owner:* M13 è diventata "attach" (§7, ADR 0037); il prompt neutro ci sta dentro, report e persistenza no (proposta M17). L'esperimento si fa attaccando il repo legacy, non copiandolo dentro lights-out.
2. **L'esperimento pubblico.** lights-out puntato su un repo legacy open source noto, in un ecosistema con un mutation tool serio (Java/PIT, .NET o JavaScript/Stryker), su un lotto di ticket meccanici — upgrade di dipendenza, dead code, test su codice non testato, migrazione di API deprecate. Catena di audit pubblicata, fixture replayabili, ispezionabile senza chiave. **Criterio di uscita:** se almeno due ticket su tre non producono una PR mergiabile senza che un umano tocchi il codice, la tesi dell'harness è più debole del previsto e A non si costruisce sopra.
   *Emendamento 2026-09-23, decisione dell'owner:* **Python** (anche un'app Django, se il candidato lo richiede). Java, .NET e JS mescolavano due domande — la tesi (gli agenti fanno modernizzazione meccanica sotto i gate?) e l'indipendenza dal linguaggio — e la seconda costa lavoro di piattaforma (un'immagine worker per workload: il worker ha solo Python 3.13 e Node 24). In Python l'harness ha già tutto: cosmic-ray e il runner in-image, il gate line-scoped, bandit, osv-scanner, la toolchain nel worker. L'esperimento misura solo la tesi; l'indipendenza dal linguaggio arriva dopo, sul linguaggio del primo cliente. Da verificare sul primo ticket: il tempo di cosmic-ray sul legacy (792 s per 205 mutanti sul meetup) e una versione di Python diversa da 3.13, se il candidato la richiede.
3. ~~Il primo engagement pagato.~~ *Tolto il 2026-11-02:* il lancio pubblico costruito sull'esperimento prende il suo posto (§15). Un engagement che arriva si accetta come design partner, senza che la sequenza lo aspetti.
4. **M11 — console**, dopo l'esperimento: è quello che un talk e un README possono mostrare, e quello che un design partner vuole vedere.
5. **Il consumatore A**, se il punto 2 ha tenuto. Il loop di affinamento va progettato prima di scriverlo.
6. Track cloud di M8 e M10 quando qualcuno li paga.

### La superficie per i contributor

Subito dopo il seam, un pomeriggio e non una milestone: `CONTRIBUTING.md`; una `ROADMAP.md` in inglese derivata da questo documento (che resta il documento di lavoro, in italiano); la suite di conformità come asticella di accettazione per adapter e gate pack contribuiti (lo schema di ADR 0026 esteso oltre Delivery); e la regola di §11 estesa: un adapter contribuito senza un nightly e un maintainer è un debito, non un regalo. Quello che il repo ha già e va solo dichiarato: il contratto dei gate come regola di contribuzione (`ci/contract.sh`), `RISK_HIGH_PLATFORM` (una PR che tocca la piattaforma non si auto-mergia), e L0 senza chiave come onboarding.

Il repo su GitHub è privato al 2026-09-23; la pubblicazione è un atto dell'owner, dopo il seam e la superficie per i contributor.

## 15. Il piano di visibilità

*Aggiunto 2026-11-02 (ADR 0029, "Amendment 2026-11-02").* L'obiettivo primo è che lights-out venga provato, stellato e raccontato. Il budget è 5–15 ore a settimana: ogni voce qui sotto deve stare in quel budget o non entra.

### Cosa si misura

Stelle, clonazioni e visitatori unici (GitHub Insights → Traffic), issue aperte da esterni, contributor esterni, inviti a talk, richieste di consulenza in entrata. I numeri obiettivo li fissa l'owner prima del lancio, non dopo: un obiettivo scelto a posteriori non misura niente. Lo stesso vale per i segnali che fanno cercare attivamente un co-founder.

### Il messaggio

Una frase sola, ripetuta ovunque: *agenti autonomi che portano un cambiamento fino in produzione su un codebase di cui nessuno si fida — gate numerici, perimetro dichiarato, rollback automatico, un solo umano prima del 100%.* Il gancio che nessun altro mostra (ricerca del 2026-11-02: i guardrail open source per agenti si fermano al comando o alla PR) è **il rollback automatico di un cambiamento scritto da un agente**. Quella è l'immagine del README, la GIF, la prima slide.

Non si dice "super", non si dice "human in the loop" (lo dicono tutti): si dice *un* umano, *un* gate.

### Fase 0 — Pronto da pubblicare (settimane 1–3)

- README: headline, quickstart senza attriti, percorso breve con tempi misurati, rimando alla guida "su un repo vero" (`docs/use-on-your-repo.md`), che dichiara cosa non è ancora provato.
- `CONTRIBUTING.md` (DCO), `ROADMAP.md` in inglese, `SECURITY.md` (un harness che maneggia chiavi e codice altrui ne ha bisogno).
- Una registrazione di terminale del rollback (canary al 5%, verify NO-GO, ritorno a 100/0 da solo), da tenere sotto i 60 secondi, in testa al README.
- GitHub: descrizione, topic (`ai-agents`, `coding-agents`, `guardrails`, `canary`, `progressive-delivery`, `platform-engineering`, `devsecops`, `gemini`, `adk`), immagine di anteprima social, Discussions attive, 5–8 issue marcate `good first issue` scritte da ticket veri, una release `v0.1.0` con note.
- **Soft launch** su 10–20 persone fidate (colleghi, community italiane): l'unica domanda è "`./go demo` è arrivato in fondo sulla tua macchina?". Ogni attrito trovato qui si corregge prima del lancio pubblico. La pubblicazione del repo resta un atto dell'owner.

### Fase 1 — L'esperimento in pubblico (mesi 1–3)

M13, poi l'esperimento legacy di §14. Si costruisce in pubblico: un post breve a settimana (LinkedIn, X/Bluesky) con il diario dei ticket — GO o NO-GO, e perché. Costa poco, accumula pubblico prima del lancio e produce il materiale dell'articolo. I NO-GO si pubblicano come i GO: la credibilità di un harness di fiducia viene da lì.

### Fase 2 — Il lancio (dopo l'esperimento)

- Un articolo lungo in inglese con i numeri veri, fallimenti compresi: "abbiamo lasciato agenti autonomi a modernizzare <repo> sotto gate numerici". Sul blog dell'owner, ripreso su dev.to e Medium.
- Show HN, un solo colpo: martedì–giovedì, mattina US, con il link al repo e l'articolo. Reddit dove l'autopromozione è ammessa e pertinente (r/devops, r/Python per l'esperimento in Python). Lobsters se arriva un invito.
- Newsletter a cui si sottopone un link: Python Weekly, PyCoder's Weekly, DevOps Weekly, Console.dev, TLDR, Changelog News.
- Awesome list pertinenti, una PR ciascuna, solo dove il progetto entra davvero (agenti, platform engineering, DevSecOps, Gemini/ADK).
- Talk: le CFP si inviano durante la fase 1, con l'esperimento come storia. PyCon Italia (esperimento in Python), Codemotion, DevFest e community Google Developer (ADK, Gemini, profili L2/L3 su GCP), PlatformCon, meetup locali. Il repo è costruito per il palco: la demo dal vivo è il rollback.

### Fase 3 — Il secondo lancio

Il pacchetto dei gate indipendente dall'agente (usabile accanto a Claude Code, Codex, Copilot), con la sua ADR: il marketplace delle GitHub Action è un canale di scoperta a sé. Poi M11, la console: una catena di audit visibile vale più di un paragrafo di README.

### Il ritmo settimanale

Su 10 ore: 6–7 di prodotto, 2 di contenuti (il post settimanale, le CFP), 1 di community (issue e PR esterne con risposta entro 48 ore — un primo contributor ignorato non torna).

### Rischi

- **Quickstart rotto il giorno del lancio.** Si mitiga con il soft launch e con `./go demo` verde su Linux e macOS prima di ogni annuncio.
- **Promettere più di quanto gira.** Ogni livello non provato resta dichiarato come tale (regola "niente mock nascosti"); la guida "su un repo vero" dice cosa non è ancora stato provato.
- **Runtime solo Gemini davanti a un pubblico che usa soprattutto Claude Code e Codex.** Si risponde con la fase 3, non riscrivendo i ruoli.
- **La demo completa dura minuti, non secondi.** Il README offre prima il percorso breve.

### Cosa non fare

Comprare stelle o scambiarle. Spammare awesome list. Lanciare su HN prima dell'esperimento: il primo giudizio è quello che resta. Aprire canali (Discord, Slack) che con 10 ore a settimana non si possono presidiare: bastano le Discussions.

## 16. Il terzo arco: ingresso zero, modello a scelta

*Aggiunto 2026-11-03, decisione dell'owner.* La valutazione del 2026-11-03 ([docs/plans/assessment-and-must-have-plan.md](plans/assessment-and-must-have-plan.md)) ha concluso che lights-out oggi è un prodotto per un platform team, non per ogni sviluppatore: il valore (gate numerici, perimetro, rollback automatico, catena di audit) sta sotto otto servizi, un solo runtime di modello e un contratto pesante. L'owner ha deciso di costruire l'intero prodotto — sviluppo di feature e ops, post mortem compreso — con **complessità in ingresso nulla e modello a scelta** (Gemini, Claude, OpenAI, configurabile).

### Due principi che guidano tutto

1. **Complessità progressiva, non assente.** L'ingresso è un comando su un repo qualunque che risponde `GO`/`NO-GO` in cinque minuti senza piano, senza socket dell'engine e senza chiave. Ogni scalino successivo (l'agente, la PR su GitHub, le metriche vere, il canary) si paga solo quando serve, e ogni scalino vale da solo.
2. **Il modello è una scelta del profilo, non una costante del ruolo.** Un ruolo fissa `THINKING` e i budget; chi risponde lo dicono `MODEL_PROVIDER` e `MODEL`, nel profilo o in `.env`. Il replay a L0 resta senza modello: la regola d'oro non cambia. Il free tier di Gemini resta l'unico percorso gratuito a L1 e il README lo dice; Claude e OpenAI costano a ogni run.

**L'oggetto unificante è il record**, non i ruoli: ticket → PR → gate → release → verify → incidente → ipotesi → post mortem → ticket di fix. Un post mortem è la catena di audit letta al contrario; l'SRE è un insieme di soglie con provenienza, che è già come lights-out tratta `policy.env` e `slo.promql`. Tutto quello che il prodotto fa finisce in quel record e in un `GO`/`NO-GO`; se no è un assistente generico, e lì non ci si distingue da nessuno. I ruoli restano sei (`ci/roles.sh`): il post mortem è un compito del ruolo ops-triage, non un settimo ruolo.

### Cosa cambia nelle regole

- §5, "Un solo modello per tutti i ruoli": resta vero che un solo modello *alla volta* serve tutti i ruoli e che la leva è il thinking level; smette di essere vero che quel modello è `gemini-3.8-flash`. La tabella del thinking per ruolo vale per ogni fornitore, con una mappa per fornitore dentro l'adapter (M18).
- `CLAUDE.md`, "Due livelli di modelli": il runtime è "il modello del profilo", non un id.
- §4, tabella delle porte: `AgentHarness` guadagna `claude-code` e `codex`; `Metrics` guadagna `promql` (qualunque endpoint compatibile Prometheus, non solo il container del piano); `CodeHost` `github` passa da M10 a M21.
- Regola d'oro, una seconda misura accanto ai 900 s: **`./go init <repo> && ./go gates` sotto i 300 s su un repository qualunque, senza `./go up`** (M20, decisione dell'owner; la provenienza è il "cinque minuti" della valutazione; misurato al primo run, 2026-11-03, da clone pulito: 40 s su `workloads/minimal`, 8 s su `workloads/minimal-js`; vale per suite piccole, perché `init` misura la baseline sull'intero scope).

### La sequenza

Ogni milestone ha una ADR prima del codice, lascia `./go ci` e `./go demo` verdi, e dichiara a L0 cosa replaya. Le stime sono settimane a 5–15 ore (stima mia, non misura). M18 e M20 toccano file diversi (tranne `Makefile`, README e questo piano) e possono andare in parallelo in due sessioni in worktree, con il merge alla fine; M19 dipende da M18; M21, M22 e M23 dipendono da M20.

### M18 — Il modello è una scelta (ADR 0040)

*Nota 2026-11-03:* la ADR 0039 era già presa dal runner Gitea lo stesso giorno; M18 è ADR 0040 e i numeri successivi di §16 slittano di uno (M19 → 0041, M20 → 0042, M21 → 0043, M22 → 0044, M23 → 0045).

- `MODEL_PROVIDER` ∈ {`gemini`, `anthropic`, `openai`} e `MODEL` (l'id esatto, pinnato) nel profilo, sovrascrivibili da `.env`; `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` in `.env.example`, valori finti. L0 resta `replay`, senza provider.
- `THINKING` del ruolo mappato per fornitore dentro l'adapter, mai nel ruolo: `thinkingLevel` per Gemini, il livello di ragionamento per Claude e per OpenAI, con la mappa in un file solo per adapter (`adapters/<harness>/thinking.env`), ogni riga con la fonte verificata il giorno in cui si scrive.
- I ruoli ADK (product, ops-triage, release) scelgono il modello in `adapters/adk/lights_out_adk/model.py` con il wrapper `LiteLlm` di ADK per Claude e OpenAI; `RecordingLlm` e il replay avvolgono qualunque `BaseLlm`, quindi le fixture restano come sono e guadagnano il campo `provider`.
- `run.json` di ogni harness riporta `provider` e `model` serviti, non richiesti (la lezione di ADR 0018).
- `ci/model-free.sh`: nessun id di modello in `core/`, `gates/`, `verify/`, `roles/`; solo in `profiles/` e `adapters/`.
- *Da verificare prima di scrivere:* che ADK 2.9.1 esponga `LiteLlm` e passi il livello di ragionamento a Claude e OpenAI (le pagine lette il 2026-11-03 non sono versionate per la 2.x); la versione di LiteLLM da pinnare in `workbench/pyproject.toml`; gli id correnti dei modelli dei tre fornitori.
- **Fatto quando:** `./go ci` ha `model-free`; `./go demo` è verde a L0 senza chiave; `./go record-evals PROFILE=l1 MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5` registra almeno un ruolo ADK con un modello non Gemini e `./go demo-triage` lo replaya a L0 con `provider` nel run.json; lo stesso con `openai` e `MODEL=gpt-6.1-sol`. Stima: 2–3 settimane.

*Stato 2026-11-03 (sessione M18):* fatto tranne la registrazione non-Gemini. `MODEL_PROVIDER`/`MODEL` nei profili e in `.env`; mappa del thinking in `adapters/adk/thinking.env` e `adapters/gemini-cli/thinking.env` con la fonte per riga; i ruoli ADK scelgono Claude e OpenAI con `LiteLlm` (`reasoning_effort`, senza planner, che `LiteLlm` 2.9.1 ignora) e Gemini col modello e il planner di ADK; `run.json` riporta `provider` e il modello servito; `ci/model-free.sh` in `./go ci`; `litellm==1.106.6` nel workbench (+190 MB di immagine). Il percorso `./go record-evals PROFILE=l1 MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5` è implementato e documentato, non eseguito: la registrazione con una chiave non Gemini resta all'owner.

### M19 — Harness `claude-code` e `codex` (ADR 0041)

- Due adapter `AgentHarness` nuovi, una cartella ciascuno come `gemini-cli`: la CLI del fornitore pinnata da `package-lock.json` dentro un container, una sessione headless per run, lo stesso contratto di artefatti (`OUT/patch`, `pr.json`, `final.md`, `run.json`, `hooks.log`), l'adapter committa e non il modello (ADR 0017 §1).
- **Suite di conformità dell'harness**, `gates/harness-conformance.sh`, sul modello di ADR 0026: su un ticket stub, l'adapter produce patch e `pr.json`; un `git push` dal modello è negato e loggato; la lettura di `.env` e dei file di chiave è negata; `MAX_TURNS`, `TIMEOUT_S` e `TOKEN_BUDGET` fermano il run; `run.json` dice il modello servito; nessuna chiave negli artefatti. `gemini-cli` la passa per primo; è il requisito d'ingresso per ogni harness, contribuito compreso.
- Dove un fornitore non ha gli hook, la guardia si ottiene dal contenitore: niente credenziali git, rete chiusa, workspace in sola scrittura locale; la suite lo prova e il README dichiara quale harness ha la guardia nell'hook e quale nel contenitore.
- *Da verificare prima di scrivere:* che gli hook `PreToolUse` di Claude Code scattino in modalità `-p` e che l'exit code distingua budget esaurito da errore (fonti di comunità in disaccordo, 2026-11-03); gli eventi JSON di `codex exec --json` e le sue modalità sandbox; che entrambe le CLI accettino la chiave da variabile d'ambiente senza login interattivo.
- **Fatto quando:** `./go harness-conformance` è `GO` per `gemini-cli`, `claude-code` e `codex`; `./go record TICKET=0001 PROFILE=l1 AGENT_HARNESS=claude-code` produce una PR che passa `./go gates`, e lo stesso con `codex`; le due registrazioni entrano in `fixtures/` con `provider`; `./go demo` è verde a L0. Stima: 3–4 settimane.

*Stato 2026-11-04 (sessione M19):* fatto tranne le due registrazioni. Gli adapter `claude-code` (Claude Code 2.1.311, provider `anthropic`) e `codex` (Codex 0.166.0, provider `openai`) sono pinnati da `package-lock.json`; la guardia è lo stesso `guard.sh`, copiato identico, nell'hook pre-tool di ciascuna CLI (`BeforeTool` per Gemini, `PreToolUse` per Claude e Codex) e il contenitore è il confine per tutti e tre; Codex gira con la propria sandbox spenta (`danger-full-access`) perché bubblewrap non parte in podman rootless; la rete resta aperta, e chiuderla è la domanda aperta prima di M24 (chiusa dalla ADR 0046, sotto). I budget sono letti dal segnale di ciascun fornitore. `./go harness-conformance` esegue la CLI vera nel suo container contro un modello scritto a mano (`gates/harness-conformance/stub.py`), nove casi, senza chiave: prova l'impianto, non la capacità di un modello né il protocollo vero del fornitore. Deviazioni: la suite non sta tutta in `./go ci`, perché `ci` non ha il socket e la suite costruisce tre immagini; `./go ci` ha la metà senza engine (`harness-shape`, `hooks` esteso), la suite intera è un target a sé e un job del workflow (ADR 0041 §9); il comando di registrazione nomina fornitore e modello (`AGENT_HARNESS=claude-code MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5`, e `codex openai gpt-6.1-sol`) e scrive in `fixtures/<ticket>/<ruolo>/<harness>/`, mentre L0 continua a riprodurre quelle di `gemini-cli` e il replay non legge le nuove cartelle; il worker monta la cartella del run e non più `.crew`. Tre difetti trovati costruendo, chiusi: un `.env` del repository poteva puntare `GOOGLE_GEMINI_BASE_URL` di `gemini-cli`, chiave compresa, su un altro host; un `.claude/settings.json` con `disableAllHooks` o un `.codex/config.toml` con `[features] hooks = false` del repository spegnevano la guardia (chiusi con `--setting-sources user` e `--enable hooks`); il worker montava tutto `.crew/`, chiave di firma del rilascio compresa. Le due registrazioni (`./go record TICKET=0001 PROFILE=l1` con ciascun harness) spendono le chiavi dell'owner e restano sue; il costo per fornitore va nel README quando esistono.

*Stato 2026-11-04 (ADR 0046, prima di M24):* la rete non è più aperta. Gli harness stanno su una rete interna `crew` e l'unica uscita è il proxy `egress`, con allowlist esatta host:porta: il fornitore dell'harness più gli host che il contratto del workload elenca in `crew-egress.txt`. Il worker ha un Postgres proprio (`crew-postgres`), non quello del piano. La prova è il caso 9 della conformità, che fa leggere a una sonda la propria chiave e tenta otto uscite, tutte da bloccare: docker su Actions a ogni push, podman rootless nel workflow `podman`, con l'esito in HANDOFF. Restano canali: l'host del fornitore stesso, la chiave codificata nella PR, il DNS dove l'engine lo inoltra da reti interne.

### M20 — Gate ovunque: `./go init` e i gate senza piano (ADR 0042)

Assorbe la metà "toolchain" di M14.

- **Contratto del runner nel workload**: `.lights-out/workload.env` guadagna `TEST_CMD`, `SAST_CMD`, `MUTATION_CMD` e `TOOLCHAIN_IMAGE` (o il `Containerfile` del repo). I gate `test`, `sast` e `mutation` eseguono il comando nell'immagine della toolchain del repo; il servizio compose `backend-test` diventa una delle implementazioni, che l'app in bundle continua a usare. Il dev-worker gira nella stessa immagine: è la toolchain del repo, non più Python 3.13 e Node 24 fissi.
- **Il percorso senza socket**: `secrets`, `deps`, `risk` e il perimetro girano già nel workbench nudo; `sast` ci gira se il runner è un binario del workbench (semgrep); `test` e `mutation` girano nel workbench quando la toolchain del repo coincide con la sua, altrimenti nell'immagine del repo attraverso l'engine. La riga `GO`/`NO-GO` dice sempre dove ha girato.
- **`./go init <path>`**: legge il repo, deduce lo stack (`pyproject.toml`/`uv.lock`, `package.json`), scrive una bozza di `.lights-out/` con `worker.md`, `workload.env` e `policy.env`, ogni valore con un commento che ne dice la provenienza ("dedotto da", "misurato con `./go mutation-baseline`", "default della piattaforma"); non scrive mai nel repo dell'utente, come `attach` (ADR 0037): la bozza sta in `.attached/.lights-out/` finché l'utente la copia.
- **Secondo stack**: JavaScript con Stryker come runner di mutation, provato su un repo di esempio attaccabile; il gate di mutation legge uno score, non un tool.
- **Fatto quando:** da un clone pulito, su `workloads/minimal` come repo a sé e senza `./go up`: `./go attach`, `./go init`, `./go gates` → `GO` in meno di 300 s (misurati nel report); lo stesso su un repo JavaScript di esempio; `./go demo-gates` e `./go demo-seam` invariati; `ci/workloads.sh` controlla le chiavi nuove. Stima: 3–4 settimane.
- **Stato (2026-11-03, chiusa, ADR 0042):** `./go demo-init` è l'accettazione: su un clone pulito, cache fredde, `workloads/minimal` 40 s e `workloads/minimal-js` 8 s per `init` più `gates` nel workbench senza engine (il contratto committato giudicato prima attraverso l'engine: `compose:backend-test` e l'immagine `node:24` per digest). Quattro chiavi nuove in `workload.env` (`TOOLCHAIN_IMAGE`, `TEST_CMD`, `SAST_CMD`, `MUTATION_CMD`), tre forme per il toolchain (`workbench`, `compose:<servizio>`, un'immagine), la riga del gate dice dove ha girato, `./go gates` senza range giudica l'ultimo commit, il socket è opzionale per `gates`, `init` e `mutation-baseline`; `stacks/python` (cosmic-ray, bandit) e `stacks/javascript` (Stryker, eslint-plugin-security) con lockfile; il dev-worker si costruisce sull'immagine del toolchain quando è un'immagine (provato con `gemini --version` su `python:3.13-slim-trixie`, non a L1). Deviazioni dal piano: niente semgrep; con la forma `compose:` il worker resta sul workbench; i 300 s valgono per suite piccole (init misura l'intero scope). Dettagli e misure in `.claude/context/HANDOFF.md`.

### M21 — GitHub come code host e il rilascio di un repo attaccato (ADR 0043)

Assorbe la metà "rilascio" di M14.

- `adapters/github/`: gli stessi verbi di `gitea` (`bootstrap`, `clone-url`, `push`, `open-pr`, `status`, `merge`, `pr`, `await`) sulla REST API di GitHub con un token in `.env`, mai nel `.git/config`, mai visibile al modello. La PR del ticket arriva sul repository dell'utente; la tower la giudica con i gate della base (ADR 0033) e posta lo stato `gates` sul commit.
- Il rilascio di un repo attaccato: dopo il merge, `./go release` costruisce l'immagine del merge commit con il `Containerfile` del repo (o `TOOLCHAIN_IMAGE`; vedi la nota di stato: `TOOLCHAIN_IMAGE` è stato scartato), la firma e la verifica come oggi (ADR 0025), senza il job Gitea Actions che il repo dell'utente non ha.
- L0 resta Gitea: nessuna API GitHub registrata, nessun finto GitHub. Un nightly su GitHub Actions contro un repository usa e getta dell'owner prova l'adapter a L1 (§11, "un adapter senza nightly è un debito").
- **Fatto quando:** `./go e2e CODE_HOST=github PROFILE=l1` su un repo attaccato apre la PR su GitHub, la mergia dopo `GO: gates`, costruisce e rilascia il merge sul piano locale fino al rollback; il nightly è verde; `./go demo` invariato. Stima: 3 settimane.

*Stato 2026-11-04 (sessione M21):* costruito, ADR 0043; la prova end to end su GitHub non è stata eseguita (nessun token in sessione). `adapters/github/` ha gli otto verbi di `gitea` più `ready.sh`, `env.sh` e `credential.sh`, sulla REST API (header di versione 2022-11-28), configurato da `GITHUB_REPO` e `GITHUB_TOKEN` in `.env`. Il token va a curl su stdin (`-H @-`) e a git tramite un credential helper che il Makefile aggiunge come config d'ambiente (`GIT_CONFIG_KEY_1`): mai in argv, in un `.git/config` o nel contenitore del modello. Il rilascio di un repo attaccato, su qualunque code host (Gitea compreso), è in `core/steps/release.sh`: costruisce il merge commit in un worktree usa e getta con `make publish`, lo firma, poi la launchpad invariata verifica la firma e rilascia; l'app inclusa aspetta ancora il job `image` di Gitea. La prova: `./go ci` guadagna `codehost` (controllo a freddo di ogni adapter, registratori per curl e git, nessun finto GitHub); `./go codehost-conformance` è una suite di dieci casi sul `CODE_HOST` impostato, gira contro Gitea nel job `launch` a ogni push e contro GitHub nel nightly `nightly-github.yml`. `ci/vendor-free.sh` vieta ora `gitea|github` in `core/`. Scostamenti dal piano: `TOOLCHAIN_IMAGE` non è un artefatto di rilascio (non contiene l'applicazione); il nightly esegue la suite di conformità, non l'e2e completo, quindi "il nightly è verde" prova i verbi e non la tower su GitHub; `CODE_HOST=github` serve solo un repo attaccato e va sulla riga di comando, mai in `.env`; dopo ogni merge va rifatto `git pull` e `./go attach`; l'app inclusa tiene il job `image` di Gitea e `./go demo` è invariato. Resta all'owner: il repository usa e getta (da `workloads/minimal`, che ora porta `.lights-out/tickets/0001.md`), la variabile `LIGHTS_OUT_GITHUB_REPO` e il secret `LIGHTS_OUT_GITHUB_TOKEN` per il nightly (finché la variabile manca, il nightly salta con un avviso), e l'unica esecuzione di `./go e2e CODE_HOST=github PROFILE=l1`.

### M22 — Ops senza piano: incidente in entrata, post mortem in uscita (ADR 0044)

- Il ruolo ops-triage accetta, oltre all'alert JSON, un **incidente**: alert, record di release, estratto dei log e l'intervallo di tempo. Guadagna lo strumento `file_postmortem` (cronologia ancorata alla catena di audit, cause contribuenti, azioni correttive) accanto a `file_incident` e alle proposte; ogni azione correttiva diventa un ticket nel `Tracker`, che rientra nella tower come qualunque ticket: così il loop si chiude.
- `./go postmortem INCIDENT=<file>` scrive `.crew/postmortem/<nome>/postmortem.md` e i ticket; `NO-GO` se la cronologia non è ancorata a release e PR reali della catena di audit o se un'azione non ha un ticket.
- **La porta `Metrics` si generalizza**: l'adapter `promql` interroga `METRICS_URL`, qualunque endpoint compatibile Prometheus (Prometheus, Mimir, VictoriaMetrics, Managed Prometheus); `verify/slo.promql` resta un file solo; l'adapter `prometheus` del piano diventa il caso `METRICS_URL=http://prometheus:9090`. Così `./go verify` giudica le metriche vere dell'utente senza il piano.
- **Fatto quando:** `./go demo-postmortem` a L0, senza chiave, replaya un incidente registrato dal record di release vero di `demo-rollback` e stampa `GO: demo-postmortem` con un ticket di fix in `tickets/`; `./go verify METRICS_URL=…` contro il Prometheus del piano dà lo stesso verdetto di oggi; i ruoli restano sei. Stima: 3 settimane.

*Stato 2026-11-04 (sessione M22):* costruito, ADR 0044. `./go incident`, `./go postmortem`, `./go demo-postmortem` e `./go record-postmortem`; il quarto strumento `file_postmortem` di ops-triage; il verbo `put.sh` del Tracker `file`; l'adapter `promql`, con `prometheus` che lo chiama su `http://$PLANE_HOST:9090`. `./go demo-postmortem` è NO-GO finché l'owner non esegue `./go record-postmortem PROFILE=l1`: nella sessione non c'era la chiave Gemini, e nessuna risposta del modello è scritta a mano. I ticket della demo vanno in una copia di `tickets/`, così il checkout resta pulito; `./go postmortem` scrive in `tickets/`. `./go ci` e `./go demo` non dipendono dalla registrazione.

*Nota 2026-11-04 (owner):* registrato a L1 su gemini-3.8-flash (`./go record-postmortem PROFILE=l1`, commit a0ff191); `./go demo-postmortem` → `GO: demo-postmortem` a L0 senza chiave, un'azione, ticket di fix 0014. Il criterio di M22 è chiuso.

### M23 — Il comando unico e il pacchetto (ADR 0045)

- Un'immagine pubblicata (`ghcr.io/nicolaguglielmi/lights-out`) e un wrapper `lights-out` di poche righe che fa quello che `./go` fa dal clone: `lights-out init`, `lights-out gates`, `lights-out triage`, `lights-out postmortem` su qualunque repo, senza clonare lights-out. Il piano completo resta `git clone && ./go demo`.
- Una GitHub Action `lights-out gates` che posta la riga `GO`/`NO-GO` come check sulla PR; una ricetta documentata per chiamare `lights-out gates` da un hook di Claude Code, Codex o Gemini CLI prima del commit.
- `./go doctor`: engine, versioni, porte, chiave presente per il provider scelto, in una riga per voce.
- **Fatto quando:** su una macchina pulita con il solo engine, `lights-out gates` su un repo con `.lights-out/` risponde in meno di 300 s; la Action è verde su una PR del repo di esempio; `./go demo` invariato. Stima: 2–3 settimane.

*Stato 2026-11-04 (sessione M23, branch `claude/kind-gauss-tzw1q7`):* costruito, ADR 0045. L'immagine è il workbench più l'albero committato (`git archive HEAD`) in `/opt/lights-out`, costruita da `package/build.sh` con un contesto solo, che vale per podman, docker e buildx multi-piattaforma; 1,77 GB. Il wrapper `lights-out` (POSIX sh, podman o docker, git) esegue `init`, `gates`, `triage`, `postmortem`, `doctor`, `version`: il repository montato in sola lettura, una cartella di output (`~/.local/state/lights-out/<repo>`), le chiavi per nome dall'ambiente, mai `.env`, **mai il socket dell'engine**, quindi solo `TOOLCHAIN_IMAGE=workbench` passa dal wrapper (`compose:` e immagine danno NO-GO con il motivo). Un range è giudicato dal contratto della sua base (`workload.env`, `policy.env`, `runners/`); `STAGED=1` giudica lo staged come un commit, per le ricette degli hook. `./go doctor` sull'host, una riga per voce. La Action composita `action/` posta la riga come check run. Accettazione su GitHub Actions: `./go demo-package` → `GO: demo-package — init and gates 51s in workbench (budget 300s), a staged break NO-GO at test` (run 41826312637); il test della Action posta un check `success` sul GO e uno `failure` sul NO-GO; `ci`, `engine-compat` (`GO: demo`, 689 s), `gates` verdi. Deviazioni: la Action è provata nel workflow di lights-out (`uses: ./action` su un repo di prova), non su una PR di un altro repository, che richiede la prima pubblicazione; l'immagine **non è pubblicata**: il job `publish` (tag `v*` o dispatch, amd64+arm64 con QEMU) non è mai girato e resta all'owner, come rendere pubblico il pacchetto; le ricette degli hook per Codex e Gemini CLI non sono state eseguite contro le CLI vere.

*Nota 2026-11-04 (dopo M23, ADR 0033 emendata):* chiuso il buco trovato da M23: anche il passo `ci` della torre prende dalla base di una PR su un repo attaccato `.lights-out/runners/`, oltre a `workload.env` e `policy.env`, lo stesso insieme del wrapper (ADR 0045 §3); una PR che riscrive un runner per far passare un gate è giudicata dal runner della base, provato da `ci/attach.sh`.

### M24 — L'esperimento pubblico, con qualunque fornitore

*Nota 2026-11-03:* le ADR di questo arco sono 0040–0045, non 0039–0044 come scritto in prima stesura: 0039 era già presa (il runner Gitea esegue solo il job image). M18 ha scritto ADR 0040.

L'esperimento di §14 come scritto, ma ogni ticket gira con i tre fornitori e il diario pubblica i tre verdetti: è la risposta al rischio "runtime solo Gemini" di §15, e il materiale del lancio di fase 2. Il criterio d'uscita di §14 non cambia. Stima: 8–12 settimane, in parallelo con la fase 1 di §15.

### M25 — Delivery su Kubernetes: `argo-rollouts` (ADR 0051)

Il terzo candidato di ADR 0024 §5, costruito. Oggi un team che rilascia già su Kubernetes deve scrivere un adapter prima che lights-out gli serva; con questo adapter sceglie `DELIVERY=argo-rollouts` e ha canary, verify e rollback del launchpad sul suo cluster, senza Envoy e senza il percorso di delivery del piano compose. Zero modifiche a `core/`.

- `adapters/argo-rollouts/`: i quattro verbi e `ready.sh`, solo `kubectl` (aggiunto al workbench, pinnato). Il Rollout dichiara i passi `setCanaryScale` + `pause`, poi `setWeight` 5, 25, 100 ognuno seguito da `pause`; `shift.sh` promuove una pausa alla volta, `rollback.sh` fa abort, `status.sh` legge dai pod e dal router. Serve un traffic router: senza, il 5% esatto vuole 20 repliche.
- La prova locale è un nodo k3s accanto al piano L0, servizio compose `k8s` dichiarato nell'adapter: Registry, Flags e Metrics restano quelli del piano, si sposta solo il Delivery. Il workload ottiene una parte opzionale del contratto, `k8s/`; `app/k8s/backend.yaml` è quella dell'app.
- Sotto podman serve un engine rootful: la macchina podman rootless non delega il controller cpuset che k3s chiede (misurato il 2026-11-06). `CONTAINER_CONNECTION=podman-machine-default-root` lo dà senza cambiare impostazioni.
- **Fatto quando:** `./go up && ./go argo-conformance` stampa `GO: delivery-conformance` in locale e nel job `argo` di GitHub Actions, con `gates/delivery-conformance.sh` invariata; `./go ci` verde; `./go demo` invariato e senza cluster.

### M26 — Il confine della shell (ADR 0052)

*Aggiunto 2026-11-06, decisione dell'owner.* Il repo è 16,8k righe di shell contro 6,1k di Python, e in `core/` la shell teneva una macchina a stati e schemi JSON scritti in `jq`, fuori da ogni test unitario e dal punteggio di mutation del gate di sé (ADR 0049).

- **Il confine.** La shell resta dove è il contratto o l'host: `./go`, `lights-out`, i file di `core/` che girano sull'host prima di ogni immagine (`doctor.sh`, `attach.sh`), i verbi degli adapter (ADR 0024), il wrapper del gate che stampa l'unica riga, gli entry point sottili e la colla che lancia processi. La logica (parsing, decisioni, macchine a stati, JSON) va in Python sotto `core/`, solo libreria standard, con test `unittest` scritti dalle ADR.
- **Il controllo** `ci/shell-boundary.sh` in `./go ci`: un file shell di `core/` ha al massimo 30 righe di codice (decisione dell'owner, misurata sulla colla di oggi). Chi le supera oggi è elencato col conteggio esatto: un debito che può solo scendere, e la voce si abbassa o si toglie quando scende.
- **La prima fetta:** `tower.sh`, `audit.sh`, `incident.sh` e la logica di `triage.sh` passano in `core/*.py` dietro gli stessi entry point; `Makefile`, `./go` e la torre non cambiano.
- **Dopo:** il resto di `core/` (la lista del debito), poi le suite di `ci/` e `gates/`; gli adapter solo dietro i loro verbi.
- **Fatto quando:** `./go ci` verde con `shell-boundary`; `./go demo` verde da clone pulito, senza chiave, sotto i 900 s; le righe shell di `core/` scese di quanto la fetta ha spostato.

*Stato 2026-11-06 (sessione M26, branch `claude/shell-boundary-7f7be1`):* ADR 0052 scritta; `core/` da 2.101 a 1.764 righe shell (codice: da 1.357 a 1.074); 103 test unitari nuovi (mutation 0,866 sui quattro moduli, 701 mutanti); dodici file restano nella lista del debito. `./go ci` verde da clone pulito; `./go demo` → `GO: demo, milestone M9, 463s to rollback`, da clone pulito senza `.env` né chiave, su un piano libero. Approvata dall'owner per main; scritta come M25 e rinumerata M26 al merge, perché M25 è `argo-rollouts` (ADR 0051).

### M27 — Il test che non prova niente, e due ticket sugli stessi file (ADR 0053)

*Aggiunto 2026-11-07, decisione dell'owner.* Prima di M24: su un repository che non conosciamo, il verdetto vale quanto i test che lo sostengono. Oggi il test finto lo prende la mutation, solo dove la mutation gira (Python), e lo cerca il `test-reviewer`, che è un modello. Quattro controlli deterministici, nessun ruolo nuovo, nessun modello.

- **Fallisce prima, passa dopo.** I test che la PR aggiunge o modifica girano sulla base, con il solo cambio dei test applicato: devono fallire. Sulla head devono passare. Quali file sono test lo dichiara il contratto del workload. Vale per ogni runner, JS compreso. Una PR che non tocca test non ha soggetto e passa per assenza, come la mutation (ADR 0015 §3).
- **Test indeboliti.** Il diff non può togliere asserzioni, aggiungere skip o xfail, né cancellare un test esistente, a meno che il ticket lo dichiari. È un controllo sul diff, per linguaggio, con la lista dei pattern nell'ADR e la sua provenienza.
- **Perimetri sovrapposti.** Ogni ticket dichiara il suo `## Perimeter` (ADR 0021 §5). `assign` rifiuta un ticket il cui perimetro si sovrappone a quello di un ticket aperto: un file, un solo worker alla volta. Il ticket resta in attesa e non viene scartato.
- **Base verde prima del primo ticket.** Su un repository attaccato, `assign` parte solo se i gate sono verdi sulla base: un NO-GO ereditato non viene addebitato al worker.
- Ognuno è un gate o una precondizione della torre col contratto a una riga. La logica sta in Python sotto `core/` (ADR 0052).
- **Fatto quando:** `./go demo-gates` ha tre fixture nuove: un test che passa già sulla base (NO-GO), un'asserzione tolta (NO-GO), un controllo positivo (GO). `./go ci` prova la sovrapposizione dei perimetri senza engine. `./go demo` resta invariato, senza chiave e sotto i 900 s.

*Stato 2026-11-07 (sessione M27, branch `claude/m27-test-proof-f96c5b`):* ADR 0053 scritta. `workload.env` ha dodici chiavi: `WORKLOAD_TEST_PATHS` dice quali file sono test (le quattro contract del repo e `./go init` la portano). Due gate nuovi, `GATES := risk secrets test-weakening deps sast test mutation test-proof`: `test-weakening` conta per file asserzioni, test e skip tolti o aggiunti (pattern Python e JavaScript nell'ADR, con la fonte) e scusa solo i file di una sezione `## Removes tests` del ticket, che il passo CI della torre passa come `GATES_TICKET`; `test-proof` porta sulla base i soli file di test cambiati e lancia `TEST_CMD` dove lo lancia `test`: se passa è NO-GO. Per assenza passano una PR senza test, una di soli test e una base albero vuoto. `test-proof` va dopo `mutation` perché `fake-test` resta l'unica prova che la mutation sa dire NO-GO. Il passo `assign` della torre ha due precondizioni: `core/assign.py` rifiuta un ticket il cui perimetro si sovrappone a quello di un ticket con PR aperta e non mergiata (un documento `perimeters/held` nello StateStore, nessun verbo nuovo); `core/base-gates.sh`, solo su un repo attaccato, giudica la base con `sast` e `test` e mette in cache il GO per commit. Il ticket rifiutato resta `opened` con il tentativo nella storia, e `./go resume` lo riprende. `./go ci` verde da clone pulito (37 check, `assign` nuovo; test unitari da 298 a 368, sopra M28); `./go demo-gates` → `GO: demo-gates`, nove fixture, le tre nuove `test-passes-on-base` (NO-GO a `test-proof`), `assertion-removed` (NO-GO a `test-weakening`), `test-edited` (GO), e `honest-fix` GO con `test-proof` che gira davvero. `./go demo` e il resto li prova Actions sulla head del branch (decisione dell'owner, stesso giorno: il motore locale è condiviso da quattro sessioni). Scostamento dal piano: "un ticket aperto" è un ticket con PR aperta e non mergiata, non ogni ticket con `Status: open` in `tickets/`, che sono quasi tutti su `app/`.

### M28 — La mappa del progetto, ricostruita a ogni merge (ADR 0054)

*Aggiunto 2026-11-07, decisione dell'owner.* Gli agenti oggi capiscono il repository con grep e con `worker.md`. Non vedono quali ADR governano un percorso, quali test lo coprono, quali ticket l'hanno già toccato, quali documenti lo descrivono. Intanto la documentazione deriva a ogni merge: `ci/readme.sh` controlla solo i comandi `./go` del README.

- **La mappa è un file SQLite** (`sqlite3`, libreria standard), mai un servizio. Nodi: funzionalità, ticket, file, simboli, test, ADR, pagine di documentazione. Archi: ticket→file, test→file, ADR→percorso, documento→percorso, comando o chiave. Le funzionalità le dichiarano i ticket, con un'etichetta: la mappa non le indovina.
- **Si ricostruisce, non si aggiorna.** Dopo ogni merge un passo della torre la rigenera da zero, in modo deterministico e senza modello. Le fonti sono i ticket, la storia git, le ADR, i documenti e il codice (`ast` per Python, un parser minimo per JS). Porta lo sha del merge: chi la legge su una base diversa fallisce con un messaggio chiaro. Una mappa stantia non si può usare senza saperlo.
- **Deriva della documentazione.** Un gate deterministico: un documento che cita un percorso, un comando `./go` o una chiave di profilo che non esiste più è NO-GO. Un merge che tocca file governati da un'ADR o descritti da una pagina apre un ticket di documentazione per il `dev-worker`, con il perimetro sui soli documenti, come il post mortem apre il ticket di fix (ADR 0044). Nessun ruolo nuovo, nessuna riscrittura senza gate.
- **Agli agenti arriva nel brief.** In `assign` la torre interroga la mappa per i file del perimetro e mette la fetta nel documento d'ingresso del worker (ADR 0031 §2): ADR, test, ticket passati, documenti da tenere allineati. Vale per ogni harness e si replaya a L0. Un server MCP in sola lettura viene dopo, e solo se M24 mostra che agli agenti serve chiedere a metà lavoro.
- **Si misura in M24.** Un interruttore di profilo mette o toglie la fetta dal brief. In M24 metà dei ticket gira con la mappa e metà senza, e si confrontano turni, token e tentativi di rework dai `run.json`.
- **Fatto quando:** `./go map` costruisce la mappa su lights-out e su un workload attaccato. `./go ci` prova che una mappa con sha diverso è rifiutata e che il gate di deriva è verde sulla documentazione di questo repository, con un caso NO-GO costruito. `./go demo` resta invariato, senza chiave e sotto i 900 s.

*Stato 2026-11-07 (sessione M28, branch `claude/m28-project-map-0cf85c`):* ADR 0054 scritta prima del codice. `core/map.py` (solo libreria standard) e `./go map`: su 105dea2 la mappa di questo repository si costruisce in 0,5 s, 548 file, 18 test, 51 ADR, 45 pagine, 13 ticket, 612 simboli. Il passo di merge la ricostruisce e apre un ticket di documentazione (nel demo, in una copia dei ticket: `[merge] map at …, docs ticket 0014`). `ci/docs-drift.sh` sostituisce `ci/readme.sh` e ha trovato tre derive vere in `docs/ARCHITECTURE.md` (l'immagine cloud di ADR 0028 descritta come costruita, ma non esiste; un link sbagliato), corrette. `MAP_BRIEF=off` in tutti i profili finché M24 non misura la fetta; il replay non dipende da `input.md`, quindi nessuna fixture toccata. 116 test unitari scritti dall'ADR, che hanno trovato quattro bug prima del merge. `./go ci` verde da clone pulito; `./go demo` → `GO: demo, milestone M9, 670s to rollback` sul job `engine-compat` di GitHub Actions (clone pulito, senza chiave, 4280b10).

### M29 — La fase dev visibile, dalla richiesta al rilascio (ADR 0055)

*Aggiunto 2026-11-07, decisione dell'owner.* Oggi la torre parte da `opened`: la raccolta della richiesta e la definizione della spec non lasciano traccia, e una richiesta ambigua si scopre solo dopo quattro giri di rework. La console di M11 vede la fase dev, ma non è su main.

- **Prima il recupero della console.** `merge/console` (ADR 0047: il logbook, cinque schermate, il go-for-launch attraverso `core/promote.sh`) riallineato su main e portato dentro con la sua CI. I campi di costo che il logbook scriveva in `core/tower.sh` vanno nel modulo Python della torre (ADR 0052).
- **Tre stati prima del ticket:** `requested` → `questions` → `spec-ready` → `opened`. Il ruolo `product` legge la richiesta e restituisce domande, oppure dice che è chiara. Le risposte arrivano da `./go answer` o dalla console: è la seconda scrittura che ADR 0023 §2 già prevede. Si registrano chi ha risposto e quando.
- **Il gate sulla spec**, deterministico: criteri Given/When/Then, un `## Perimeter`, nessun criterio senza un esito osservabile. Un NO-GO riporta il ticket a `questions` con il motivo.
- **La timeline del ticket**, una riga per fase, ognuna col suo record:
  - richiesta, domande e risposte, verdetto della spec;
  - `assign` con perimetro e attesa (M27);
  - tentativi del worker con turni, token e costo, ogni gate con la sua riga, review, rework;
  - merge, canary, firma umana, 100% o rollback.
- **La vista d'insieme:** i ticket per stato, la mappa dei perimetri occupati (M27) e i documenti che un merge ha lasciato da riallineare (M28).
- **Il kanban** (*aggiunto 2026-11-07, decisione dell'owner*): una colonna per stato della torre, compresi i tre nuovi; una carta si sposta solo quando la torre sposta il ticket, niente drag-and-drop. Feature e priorità sono campi d'intestazione del ticket, versionati con lui (`- Feature: <slug>`, `- Priority: P0..P3`), controllati dal gate sulla spec se presenti; senza, il ticket resta valido e risulta "non prioritizzato". Filtri e raggruppamento per feature e priorità; dentro una colonna, priorità poi anzianità. La console resta in sola lettura su questi campi e la priorità non ordina la torre (ADR 0055 §7). `./go ci` prova che la colonna di ogni carta è lo stato del suo ticket.
- Le regole della console restano quelle di ADR 0023: è una vista e non la fonte di verità, ogni schermata ha il suo `./go`, nessun numero senza un record dietro. La registrazione del passo `questions` a L1 resta all'owner, come per M18: nessuna fixture scritta a mano.
- **Fatto quando:** `./go console` mostra a L0, senza chiave, un ticket da `requested` al rollback in una timeline sola. `./go ci` prova la tabella degli stati nuova e il gate sulla spec (un GO, un criterio vago NO-GO, un perimetro mancante NO-GO). `./go demo` resta invariato, sotto i 900 s.

*Stato 2026-11-07 (sessione M29, branch `claude/m29-dev-visible-90a231`):* prima il recupero della console, un commit a sé: `merge/console` portato dentro con un rebase in un commit solo, non un merge, perché cinque dei suoi sette commit avevano un autore diverso da quello del progetto e il golden del logbook conteneva una riga, il nome della soglia di latenza come valore di un campo `key`, che la scansione della storia legge come un segreto; il branch resta com'era. I campi di costo non stavano in `core/tower.sh` ma negli step e in `promote.sh`/`launchpad.sh`: sono andati in `core/tower.py task` e in `core/releases.py`, e il debito di shell-boundary è sceso invece di salire. Recupero verde da clone pulito: `./go ci`, `./go demo` (483 s) e `./go demo-console`. Poi ADR 0055, scritta prima del codice: `requested` → `questions` → `spec-ready` → `opened` nella tabella della torre, `./go request` e `./go answer` (chi, come, quando), il gate `spec` deterministico, la timeline, la vista d'insieme e il kanban nella console, il logbook a 1.1. A L0 il ruolo `product` gira solo dove c'è una registrazione: per il ticket 0001 non c'è, la riga dice "non consultato" con la ragione del replay e il gate giudica i criteri del ticket; `./go ci` (`ci/dev-phase.sh`) porta la richiesta registrata di 0005 da `requested` a `questions`, risposta, `spec-ready` e NO-GO per perimetro mancante, sul replay vero. Il kanban legge `- Feature:` e `- Priority:` dall'intestazione del ticket, non ha drag-and-drop, e la colonna di ogni carta è provata uguale allo stato. Dopo il landing di M27 e M28 la console legge i loro record veri: l'attesa da un `assign` rifiutato con chi tiene i file (`perimeters/held`), i ticket di documentazione dal `map` del merge. Test unitari da 368 a 459. `./go ci` verde da clone pulito; su GitHub Actions (run 42406976968, head 1bb611b, clone pulito, senza chiave) `./go demo` → `GO: demo, milestone M9, 681s to rollback`, con la torre da `requested` (`clarify` 3 s, `GO: spec`), e il logbook del demo mostra il ticket 0001 in una timeline sola da `request` al rollback, con la carta nella colonna `rolled-back`; `./go demo-console` GO nel job `launch`. Scostamenti: il worker legge ancora `tickets/<id>.md`, non la spec con i criteri confermati (il primo cambio dopo questo); i titolari di un'attesa sono letti all'ora del logbook, perché la torre non registra il motivo di un passo fallito; un ticket in attesa risulta `stranded` nell'esito, come qualunque passo fallito.

### M30 — Main sempre verde, senza coda (ADR 0056)

*Aggiunto 2026-11-07, decisione dell'owner.* Con più ticket in volo, una coda con un lock globale diventa un imbuto: ogni PR aspetta che la precedente sia rigiudicata sulla nuova base. Qui il conflitto si previene a monte (M27, perimetri) e si cura a valle, su main, con il revert del colpevole. È lo stesso principio del canary: si verifica e si torna indietro da soli.

- **Merge senza rigiudizio quando i perimetri sono disgiunti.** Una PR giudicata su una base che nel frattempo si è mossa entra senza ripetere i gate, se nessun merge successivo al suo giudizio ha toccato file del suo perimetro. Altrimenti torna al `dev-worker` come rework sulla base nuova (ADR 0038), con il motivo. Nessun ruolo integratore.
- **Main controllato dopo il merge.** Un passo della torre esegue i gate del workload sulla head di main dopo ogni merge, o su un gruppo di merge con un limite dichiarato nell'ADR con la sua provenienza.
- **Bisezione e revert.** Se main è NO-GO, la torre bisseziona fra l'ultimo main verde e la head, trova il merge colpevole, lo annulla con un revert attraverso il code host e riporta il suo ticket a rework con il verdetto. Main torna verde senza una persona.
- **Main rosso ferma il resto.** Finché main è NO-GO, `assign` e il rilascio sono bloccati, come con `release-freeze` (ADR 0013 §6), e il motivo è nel documento della torre.
- **Fatto quando:** `./go demo-mainline` mostra a L0, senza chiave: due ticket con perimetri disgiunti entrano senza rigiudizio; un terzo si sovrappone a un merge successivo e torna a rework; un merge che rompe main viene trovato per bisezione e annullato, e main torna GO. `./go ci` prova i casi della regola di rigiudizio senza engine. `./go demo` resta invariato, sotto i 900 s.

*Stato 2026-11-07 (sessione M30, branch `claude/m30-mainline-f7ffa4`, sopra M27 e M28):* ADR 0056 scritta prima del codice e rivista prima dei test: il rilascio porta il main verde che contiene il merge, non il merge da solo; main rosso ferma anche `rework`; un rework non resetta più main a L0; i perimetri di M27 restano tenuti fino a `main-green`. `core/mainline.py` (solo libreria standard): il passo di merge applica prima la regola di rigiudizio (commit di primo genitore dopo la base giudicata, file toccati contro il perimetro del ticket letto col parser di M27); il passo nuovo `mainline` (stato `main-green` fra `merged` e `release`) giudica main con i soli gate d'albero `sast test`, a gruppi di al massimo quattro commit (`policy/mainline.env`), bisseziona un gruppo rosso, annulla il colpevole con push, open-pr e merge del code host e rimanda il suo ticket a rework; la torre rifiuta `assign`, `rework` e `release` finché il documento `mainline/main` è rosso. Test dall'ADR: `core/tests/test_mainline.py`, i casi della torre e di `assign`, `ci/mainline.sh` in `./go ci`, senza engine (442 test unitari nel workbench). GitHub Actions su `c824de0`, cinque workflow verdi (run ci 42407872153): job `mainline` → `GO: demo-mainline` in 444 s col piano (0020 e 0021 mergiati su un main mosso senza rigiudizio; 0022 rimandato a rework per il merge di una persona su `db.py`; main NO-GO, bisezione in due run al merge di 0021, revert attraverso Gitea, main GO per la regola dello stesso albero); `engine-compat` → `GO: demo, milestone M9, 729s to rollback` (stranger 780 s), dove il passo `mainline` di `e2e` costa un fetch. Trovato: il bootstrap Gitea a L0 forzava main a ogni crew (ora solo al tentativo 1; resta per un `assign` dopo un merge nello stesso run); Gitea risponde 405 se si mergia mentre ricontrolla una PR la cui base si è mossa (l'adapter ora riprova fino a `READY_TIMEOUT`; l'adapter GitHub non è provato su questo caso); il piano dice "i gate del workload", l'ADR li restringe di proposito a `sast test`; la provenienza di `MAINLINE_GROUP_MAX=4` è la decisione dei quattro tentativi al giorno del free tier, da confermare dall'owner per gli altri fornitori; i test d'integrazione di `mainline` allungano la suite `unittest` che il gate di sé usa per la mutation di `core/`.

### M31 — L'ingresso a gradini (ADR 0057)

*Aggiunto 2026-11-07, decisione dell'owner. Si costruisce dopo M27–M30.* Chi passa per curiosità e chi vuole andare in produzione oggi entrano dalla stessa porta: un README lungo e un demo da 15 minuti. Una scala in cui ogni gradino chiede un solo prerequisito in più e restituisce un risultato visibile.

- **I gradini:**
  - 0, guarda (1 min, un browser): il sito, i video, l'explainer della board;
  - 1, provalo sul tuo repo (5 min, podman o docker, nessuna chiave): `lights-out gates` o la GitHub Action sulle PR del tuo agente;
  - 2, il giro completo (15 min, il clone): `./go demo`;
  - 3, agenti veri sul tuo repo (1 ora, una chiave): `./go init`, poi i ticket a L1;
  - 4, produzione (L2/L3): code host, delivery, metriche, policy, gate umano.
- **Un'immagine snella per il gradino 1.** Solo i gate, senza il piano e senza gli harness. L'immagine di oggi pesa 1,77 GB (ADR 0045); la misura nuova va nell'ADR. Pubblicarla resta all'owner.
- **`./go doctor --level <l0|l1|l2|l3>`**: cosa manca per quel livello, una riga per voce, invece di scoprirlo per errore.
- **Configurazione a strati.** `init` deduce i default; ogni chiave ha un valore di partenza e un commento con la provenienza; `docs/production.md` ha un capitolo per decisione: fornitore e budget, rischio, rework, delivery, metriche, gate umano.
- **Il gate `production-readiness`.** GO solo se il delivery è un adapter con rollback reale che ha passato la sua conformità, se le metriche arrivano da un endpoint vero, se i segreti non stanno in `.env` e se il gate umano è configurato.
- **Il README segue la scala**, gradino per gradino, e dichiara i requisiti misurati: con la VM podman da 4 GiB regge un run pesante alla volta (osservato il 2026-11-07, due arresti della VM con due demo insieme).
- **Fatto quando:**
  - il README è in quest'ordine e `ci/docs-drift.sh` (che ha sostituito `ci/readme.sh` in M28) riconosce ogni comando che cita;
  - `./go doctor --level l2` su un clone a L0 elenca le voci mancanti;
  - `production-readiness` è NO-GO a L0 e GO su un caso costruito con adapter reali locali (`argo-rollouts`, `promql`);
  - l'immagine dei gate passa `./go demo-package` con la sua misura;
  - `./go demo` resta invariato.

*Emendamento 2026-11-08 (roadmap di adozione, [docs/plans/adoption-roadmap-2026-11.md](plans/adoption-roadmap-2026-11.md), da confermare dall'owner).* M31 è la porta d'ingresso del prodotto, non un gradino fra gli altri, e guadagna quattro cose: (a) gcloud e terraform escono dall'immagine base prima di costruire quella dei gate (ADR 0028 lo decideva, `workbench/cloud` non è mai stato costruito, circa 470 MB); (b) `action.yml` passa alla radice del repository, perché il Marketplace delle Action non elenca una sottocartella, e la Action viene pubblicata lì; (c) due Action standalone sulla stessa immagine, `test-proof` e `test-integrity` (test-weakening più mutation sulle righe cambiate), ciascuna con la sua pagina: la ricerca del 2026-11-08 ha trovato cinque repository che le hanno reinventate a mano negli ultimi sessanta giorni e nessuna installabile; (d) il README dichiara come riuso il gate umano (la pausa indefinita di Argo Rollouts, il `confirm-promotion` di Flagger) e la regola della policy della base (il `pull_request_target` di GitHub dal 2025-11-07), con i link. **Fatto quando**, in aggiunta ai criteri sopra: un check postato su una PR di un repository che non è lights-out, sotto i 300 s compreso il primo pull, misurato nel README; la misura dell'immagine dei gate nell'ADR; tre pagine del Marketplace pubblicate.

*Stato 2026-11-08 (sessione M31, branch `claude/m31-front-door-9de845`, sopra 30ca9dc):* ADR 0057 scritta prima del codice (0028 emendata, 0004 e 0045 nello stato); i test (`ci/readiness.sh`, `ci/package.sh`) scritti da un subagente dall'ADR senza vedere l'implementazione. gcloud e terraform fuori: un Containerfile, due stadi (`gates`, poi `workbench` sopra). L'immagine completa passa da 1,77 GB a 1.246 MB, quella dei gate pesa 508 MB (amd64, run package 42519069964; 529 MB su arm64): sopra i 400 MB proposti dalla roadmap, e vale la misura. Dentro ci sono git con perl e python3, node, osv-scanner, uv e gitleaks; gli header C di node (65 MB) sono stati tolti. `PACKAGE_FLAVOUR=gates` e `./go package-gates`; il wrapper 0.3.0 usa l'immagine dei gate per init, gates e i nuovi `test-proof` e `test-integrity`; l'immagine scrive un riassunto con una riga per gate. `action.yml` alla radice (`action/` tolta: `@v0.2.0` resta valido sul suo tag), input `gates`, il riassunto nel check run; le due Action standalone come shim in `actions/`. Firma keyless con l'OIDC di GitHub (decisione dell'owner), solo nel job di publish. `./go doctor --level <l>`; il gate `production-readiness` e il record di conformità scritto dalla suite di delivery; `./go` passa per nome i segreti che `.env.example` dichiara. README nei cinque gradini con i due riusi dichiarati e linkati; `docs/production.md`; il track cloud e `antigravity-cli` in `docs/reference.md`. Prove: `./go ci` verde da un clone pulito (273 s, locale); GitHub Actions su 0a0d073, sei workflow verdi (ci 42519069855, stranger 42519069911, self 42519069842, site 42519069848, package 42519069964, podman 42519069828): `GO: demo, milestone M9, 848s to rollback` (engine-compat) e 782 s (stranger); `GO: demo-package` con init e gates in 48 s sull'immagine dei gate; nel job `argo` `production-readiness` è NO-GO coi default di L0 e GO su argo-rollouts (record della conformità vera) con promql sul Prometheus del piano. Su un repository che non è lights-out, `nicolaguglielmi/lights-out-probe` (PR #1, run 42519118155), i tre check sono postati GO in 19, 2 e 17 s, con l'immagine costruita nel job in 23 s. Scostamenti: il Marketplace elenca una sola Action per repository, dalla radice (docs.github.com, verificato oggi): le due standalone vogliono due repository loro, che crea l'owner con la checklist, e le tre pagine restano all'owner; `pull_request_target` è annunciato il 2025-11-07 e in vigore dal 2025-12-08, e prende il branch di default, non la base: il README lo dice così; il primo pull non si misura prima della pubblicazione; il probe privato non partiva (la fatturazione Actions dell'account ha rifiutato il job) e l'owner l'ha reso pubblico; doctor non nomina chiavi né vendor (`ci/vendor-free.sh`), le credenziali le dichiarerà l'adapter; nell'immagine dei gate il controllo del contratto non rende la metà del piano (niente docker-compose) e lo dice; trovato e corretto: con podman machine `STAGED=1` leggeva un `.git/index` vecchio attraverso il mount e giudicava un altro cambio, ora la patch la scrive il git dell'host; la provenienza dei default dei profili sta in `docs/production.md`, perché i profili sono di M34; dopo il merge di M34 (8085 e 8086 tolte, `ci/gitea-compat.sh` cancellato) doctor, README e tutorial vanno allineati.

*Stato 2026-11-09 (rilascio 0.3.0):* `pyproject.toml` a 0.3.0 come il wrapper (b931688), `main` portato lì a workflow verdi, tag `v0.3.0` spinto. `package.yml` (run 42588480235) ha costruito, pubblicato e firmato le due immagini al primo tentativo; entrambe rispondono a un pull anonimo; le due firme verificate con il cosign del workbench (3.1.3). Primo pull misurato sul probe con l'immagine pubblicata, un job per Action su un runner che non l'aveva mai tirata: 27 s l'Action alla radice, 14 s `test-proof`, 25 s `test-integrity`, tutti GO (run 42589663783 del probe), dentro i 300 s. Il wrapper del tag su un Mac arm64 ha tirato l'immagine e stampato `GO: gates` in 46 s. Creati lo stesso giorno, su richiesta dell'owner, i due repository delle Action separate, `nicolaguglielmi/test-proof` e `nicolaguglielmi/test-integrity`, con il tag `v0.3.0` e una release in bozza ciascuno; usati dal probe, 11 s e 23 s, GO (run 42591256328). Restano all'owner: pubblicare le tre release in bozza con la spunta del Marketplace, e PyPI. Trovato e non corretto: `gates/test-proof.sh` usa `HEAD=` così com'è dentro il worktree della base, quindi un riferimento relativo a HEAD (`HEAD=HEAD`, `HEAD=HEAD~1`) lì indica un altro commit; con `HEAD=HEAD` è NO-GO, con l'head di default, un ramo o uno sha è GO.

### M32 — Plugin esterni, altre CI, un altro deploy (ADR 0058)

*Aggiunto 2026-11-07, decisione dell'owner. Si costruisce dopo M27–M30.* Le porte sono già plugin (ADR 0024), ma un adapter vive solo dentro questo repository, e chi usa un'altra CI o un altro sistema di deploy deve aspettare noi.

- **Adapter fuori dal repo.** Un profilo dichiara un percorso di adapter esterni. Un plugin vale solo se ha passato la suite di conformità della sua porta (Delivery, CodeHost, AgentHarness), registrata per l'hash esatto dell'adapter; altrimenti la torre lo rifiuta in una riga. La tabella di §4 resta il catalogo dei nostri; quelli di terzi stanno fuori, con la loro prova.
- **Le altre CI sono superfici, non giudici.** Jenkins, GitLab CI, CircleCI e simili eseguono l'immagine dei gate e pubblicano la riga GO/NO-GO come check sul code host, come `action/` per GitHub. Il verdetto resta di lights-out e del contratto della base (ADR 0033): la torre non legge mai il verdetto di un'altra CI. Una ricetta mai eseguita è dichiarata "non provata" nel README.
- **Jenkins e GitLab CI provati in locale.** Jenkins con Jenkinsfile Runner in un container; GitLab come adapter CodeHost accanto a Gitea e GitHub, con la sua conformità.
- **Un adapter di deploy in più, scelto dalla domanda.** Flagger sul k3s di M25 è il più economico. Spinnaker è un adapter Delivery, non una CI, e solo su richiesta di un utente reale: non sta in piedi a L0.
- *Da verificare prima di scrivere:* le versioni correnti di Jenkinsfile Runner, di GitLab CE e di Flagger, e che si eseguano senza account.
- **Fatto quando:**
  - un adapter esterno di prova viene rifiutato senza conformità e accettato dopo;
  - `./go demo-jenkins` pubblica la riga di `lights-out gates` su una PR locale;
  - `gates/codehost-conformance.sh` è GO su GitLab;
  - `./go demo` resta invariato.

### M33 — La console come banco di lavoro: kanban interattiva, tema, ADR, spec (ADR 0059)

*Aggiunto 2026-11-08, decisione dell'owner.* La console di M29 si legge, ma non si usa per lavorare: la kanban è una fotografia, il tema segue solo il sistema, le decisioni del progetto stanno fuori, e una spec si scrive in un editor qualunque e si scopre al gate se manca qualcosa. Quattro pezzi, dentro i vincoli di ADR 0047 e ADR 0055.

- **Kanban interattiva, senza drag-and-drop.** La regola di ADR 0055 §7 resta: una carta si muove solo quando la torre muove il suo ticket. Interattiva vuol dire: un pannello laterale col dettaglio della carta (stato, verdetto, ultima riga, perimetro, attesa) senza lasciare la board; ricerca per id, titolo e file del perimetro; tastiera (frecce fra le carte, Invio apre, Esc chiude); filtri, raggruppamento e colonne vuote nel link, così una vista si condivide; colonne comprimibili; in modalità live una carta che cambia colonna si vede muovere ed è evidenziata per qualche secondo.
- **Tema chiaro e scuro.** Un interruttore nella testata, con tre valori (sistema, chiaro, scuro), ricordato nel browser; il default resta quello del sistema. Lo stesso per la board.
- **Ricerca delle ADR.** Una schermata che cerca nelle ADR per numero, titolo, stato e testo, e mostra per ognuna i file, i ticket e le altre ADR collegati. La fonte è la mappa di M28 (`.crew/map.sqlite`), non una seconda lettura del repository: l'ADR dice se la console la legge con una seconda rotta di sola lettura o se il logbook la porta in una versione 1.2, e perché. Dal dettaglio di un ticket, le ADR che governano i file del suo perimetro.
- **Le spec nella console, e la compilazione assistita.** Una schermata delle spec: per ogni ticket i criteri confermati, lo stato (`requested`, `questions`, `spec-ready`), l'ultimo verdetto del gate `spec` e la domanda aperta. Un editor per la richiesta di un ticket nuovo (titolo, contesto, criteri Given/When/Then, perimetro, feature, priorità) con un controllo dal vivo che usa le stesse regole del gate `spec`, una riga GO/NO-GO con il motivo, senza scrivere niente. Dove c'è una chiave, il ruolo `product` può fare le sue domande sulla bozza; a L0 l'editor lo dice e non finge. Salvare è una terza scrittura: l'ADR decide se la console scrive `tickets/<id>.md` e lancia la ricetta di `./go request`, con chi ha premuto e `via: console` come le altre due, oppure se consegna il file da committare a mano. Questo riapre l'editor delle spec scartato nella nota di "Dopo" (ADR 0029 §3): la regola di quell'ADR lo ammette, perché serve a un cliente con una sola istanza.
- **Fatto quando:**
  - `ci/logbook.sh` (o il suo successore) prova che nessuna interazione della kanban sposta una carta, che i filtri nel link ricostruiscono la stessa vista e che il tema non cambia nessun dato;
  - la ricerca trova un'ADR per numero, per parola del titolo e per un file che cita, su questo repository;
  - il controllo dal vivo dell'editor dà lo stesso verdetto di `gates/spec.sh` sulle stesse bozze, GO e NO-GO, provato in CI;
  - la scrittura di una spec, se l'ADR la ammette, rispetta le regole di `CONSOLE_AUTH` ed è rifiutata in snapshot;
  - README, `console/README.md`, `docs/reference.md` e le immagini del sito mostrano le quattro cose;
  - `./go demo` resta invariato.

*Stato 2026-11-08 (sessione M33, branch `claude/m33-console-7b5d5d`, sopra main 7153de5):* ADR 0059 scritta prima del codice, i test scritti da un subagente dall'ADR prima di vedere l'implementazione. La kanban ha il pannello laterale, la ricerca (id, titolo, un file del perimetro), le frecce/Invio/Esc/`/`, la vista nel link (`#kanban?q=…&collapsed=…&card=…`), le colonne comprimibili e la carta spostata dalla torre segnata 4 s con la colonna da cui viene; nessun drag-and-drop. Tema sistema/chiaro/scuro su console e board, in `localStorage` dentro un `try`; i video della board sul sito restano scuri come sono stati disegnati. Le ADR arrivano dal logbook 1.2, non da una seconda rotta: la mappa passa allo schema 2 (stato e testo di ogni ADR, archi `mentions` che il controllo di deriva non legge), ogni ticket porta le ADR che governano il suo perimetro, `/v1/logbook.json` ha un `ETag` e risponde 304. La schermata delle spec legge i campi 1.1; l'editor di una richiesta nuova controlla la bozza con `/v1/spec-check`, che esegue `gates/spec.sh` stesso su una bozza temporanea e non scrive niente; salvare è la terza scrittura (`/v1/request`: `core/spec.py draft` con creazione esclusiva del prossimo id, poi `make request` con `REQUEST_BY` e `REQUEST_VIA=console`, registrati da `core/tower.py request`), rifiutata in snapshot, in `public` e per una bozza NO-GO. Le domande di `product` passano dalla torre dopo il salvataggio, mai sulla bozza non salvata: non lascerebbero record; a L0 l'editor dice che non è consultato. Prove: 599 test unitari, `ci/logbook.sh` (golden 1.2 sulle tre ADR stub, i quattro POST, nessun drag, il controllo dal vivo uguale al gate su una bozza GO e una NO-GO per regola, la scrittura e le sue regole, il 304), e `ci/console-ui.py` con Playwright in un job `console-ui` di `ci.yml` (il workbench non ha browser): nessuna interazione sposta una carta né fa un POST, il link ricostruisce la stessa vista, il testo di ogni schermata è uguale nei tre temi e con lo storage rifiutato, l'editor dà la riga del gate, la ricerca trova un'ADR di questo repository per numero, parola del titolo e file citato. GitHub Actions su c387961, sei workflow verdi (ci 42435760042, stranger 42435759957, self 42435759934, site 42435759984, package 42435760204, podman 42435759945): `GO: demo, milestone M9, 834s to rollback` (engine-compat) e 828 s (stranger), contro 807 e 803 s dell'ultimo main: i ~25 s in più sono lo stadio `ci` del demo, che ora esegue un `ci/logbook.sh` più lungo; il margine sul budget di 900 s è di un minuto. Scostamenti: il piano chiede a `ci/logbook.sh` le prove dell'interazione, che stanno in `ci/console-ui.py` perché servono un browser; il logbook cresce del testo delle ADR (circa 700 kB qui); trovato e non toccato: gli scenari della board dicono ancora che `release` parte da `merged` (sei errori in console al caricamento, già su main da M30).

### M34 — Il piano snello (ADR 0060)

*Aggiunto 2026-11-08, proposta della roadmap di adozione ([docs/plans/adoption-roadmap-2026-11.md](plans/adoption-roadmap-2026-11.md) §4), da confermare dall'owner.* Il piano L0 porta due emulatori di Google (Pub/Sub, Firestore) e il runner di Gitea Actions per condividere codice con un L2/L3 progettato e mai eseguito (ADR 0022). Su un portatile sono tre servizi, tre pull, tre sonde di readiness e i minuti più ballerini del demo (834 s su 900 il 2026-11-08). Il prodotto è il locale (ADR 0022): il locale non paga la forma del cloud.

- **StateStore `sqlite`**: un file sotto `.crew/`, gli stessi tre verbi (`get`, `put`, `delete`), default a L0 e L1. I documenti della torre sopravvivono a `./go down` senza volume né export. `firestore-emulator` e `firestore` restano nella tabella §4 per i profili cloud.
- **EventBus `inproc`**: una coda su file con `publish`, `pull`, `ack`, default a L0 e L1; l'unico consumatore è `adapters/inproc/run.sh` nello stesso processo. `pubsub-emulator` e `pubsub` restano per il cloud.
- **Il runner fuori dal percorso del demo**: l'app inclusa viene rilasciata per la stessa via di un repository attaccato (ADR 0043 §4: il merge costruito in un worktree usa e getta con `make publish`, firmato, verificato dalla launchpad); il servizio `runner` esce dal compose di L0 e `e2e` perde l'attesa di 300 s dello status `image`. ADR 0039 e ADR 0025 §4 vengono emendate; la promessa "lo stesso YAML gira in locale e su GitHub" la mantengono i workflow su GitHub Actions.
- **La conformità come prova**: ogni adapter nuovo passa la suite della sua porta prima di diventare default; `ci/vendor-free.sh` non cambia.
- **Un budget nuovo con la sua misura**: l'ADR dichiara il budget di `./go demo` dopo il taglio, dalla misura su Actions, non da una scelta.
- **Fatto quando:** `./go demo` è `GO` da clone pulito, senza chiave, sotto il budget nuovo dichiarato nell'ADR (proposta: 600 s a caldo su Actions, da misurare); `compose.yaml` ha tre servizi in meno a L0; dopo `./go down` e `./go up` il logbook di un demo si rigenera identico; `./go ci` è verde; `./go demo-mainline`, `./go demo-rework`, `./go demo-seam` e `./go demo-console` invariati.

*Stato 2026-11-08 (sessione M34, branch `claude/m34-lean-plane-a0d988`, sopra 30ca9dc):* ADR 0060 scritta prima del codice, le due suite di conformità e `ci/store-bus.sh` scritti da un subagente dall'ADR senza vedere gli adapter. StateStore `sqlite` (`.crew/state.sqlite`) ed EventBus `spool` (`.crew/spool.sqlite`, lease di 600 s come l'`ackDeadlineSeconds` dell'emulatore), Python della libreria standard dietro i verbi `.sh`, default a L0 e L1; il bus non si chiama `inproc`, che è già l'Orchestrator. Gli emulatori restano dietro il profilo compose `emulators`, opt-in; il runner di Gitea, il job `image` e `ci/gitea-compat.sh` sono tolti, Gitea ha Actions spente, nessun servizio compose tiene più la socket del motore; `core/steps/release.sh` costruisce il merge di ogni workload in un worktree usa e getta, per l'app inclusa con il Makefile, gli adapter e la chiave del checkout ripristinati sopra quelli del merge. Servizi del piano a L0: da 8 a 5. Prove su GitHub Actions, sei workflow verdi (a0fc792: ci 42510074390, stranger 42510074189, self 42510074229, package 42510074180, podman 42510074435; site 42506965553 su e2599c8, l'ultimo commit che tocca i suoi percorsi): `GO: demo, milestone M9, 825s to rollback` (engine-compat) e 719 s (stranger); su 8fd756c 757 e 801 s, su e2599c8 873 e 852 s. `GO: demo-mainline`, `GO: demo-rework` (aggiunto al job `mainline`: nessun workflow lo eseguiva), `GO: demo-seam`, `GO: demo-console`; le due suite GO su `sqlite` e `spool` in `./go ci` e sugli emulatori nel job `launch`; dopo `./go down` e `./go up` il logbook del demo è identico byte per byte tranne `launch.plane`, l'unico campo letto dal piano vivo: `down` toglie la revisione canary tornata indietro che il demo lascia a peso 0. Scostamenti: il budget resta 900 s, perché la misura non permette di meno (i run dello stesso branch vanno da 719 a 873 s; i 600 s della roadmap non reggono: lo stadio `ci` del demo è il 43 % del tempo, ogni check gira due volte, e il build del workbench il 15 %); il guadagno di M34 su Actions è un modo di fallire in meno (l'attesa di 300 s dell'immagine), non secondi. Trovato: `demo-rework` era rotto da M30 (la sua storia attesa non aveva il passo `mainline`) e nessuno lo vedeva; l'emulatore Firestore rifiutava un array solo per un errore di jq, ora lo rifiuta per regola; lo stato della torre ora sopravvive a `./go down`, quindi un ticket bloccato o un `mainline/main` rosso restano finché qualcuno non fa `./go resume` o cancella `.crew/state.sqlite` (`docs/reference.md` lo dice). Lasciato a M31: `core/doctor.sh` e le righe del README che lo descrivono chiedono ancora le porte 8085 e 8086 libere.

### M35 — Gate senza container (ADR 0061)

*Aggiunto 2026-11-08, proposta della roadmap di adozione (§6, K2), da confermare dall'owner.* Il primo "funziona sul mio repo" costa oggi un engine e un pull da 1,8 GB. I gate che hanno bisogno solo di git e Python (`risk`, il perimetro, `test-weakening`, `test-proof` quando `TEST_CMD` è il comando del repository stesso, `spec`) girano senza engine, in secondi, da un pacchetto Python installabile con `uvx` o `pipx`.

- **Un pacchetto, due livelli, lo stesso contratto a una riga.** Il livello leggero non stampa mai `GO: gates`: stampa `GO: gates-light — 5 of 9 gates ran, 4 need the image`, così nessuno lo scambia per il giudice. I gate che servono l'immagine (`secrets`, `deps`, `sast`, `mutation`) lo dicono in una riga.
- **La logica è già Python** sotto `core/` (ADR 0052): il pacchetto espone gli entry point, non duplica niente; la shell resta dove è il contratto.
- **Le ricette degli hook** di Claude Code, Codex e Gemini CLI guadagnano `--light`, con un timeout di secondi e non di 300 s; la guida dice quali sono state eseguite contro la CLI vera.
- **Lo stesso pacchetto** ospita poi il server MCP in sola lettura di M39 (roadmap §6, K6); M35 non lo scrive.
- **Fatto quando:** `uvx lights-out gates --light` su un clone nudo di questo repository risponde in meno di 10 s e la riga nomina i gate che non hanno girato; `./go ci` prova che il verdetto leggero coincide con quello dei gate pieni sulle fixture di `./go demo-gates` dove entrambi girano; `./go demo` invariato.

*Stato 2026-11-08 (sessione M35, branch `claude/m35-light-gates-3dbc9f`, sopra 30ca9dc):* ADR 0061 scritta e committata prima del codice; gli 82 test di `core/tests/test_light.py` e `ci/gates-light.sh` scritti da un subagente dall'ADR senza leggere l'implementazione, e hanno trovato un blocco vero (lo stdin aperto di un hook fermava `git hash-object` su un commit radice). Il pacchetto `lights-out` (`pyproject.toml` alla radice, setuptools, `lights_out` mappato su `core/` con `package-dir`, nessun file spostato, solo libreria standard, Python ≥ 3.11; gli import fra moduli di `core/` diventano relativi) espone `lights-out gates --light`, `python3 -m core gates --light` da un clone. Misurato su un clone nudo di questo repository (ultimo commit, `risk high, review`): **0,14 s** con `python3 -m core`, 2,4 s con `uvx --from git+file://<clone>` al primo avvio e 0,23 s in cache; il clone resta pulito. **Scostamento dal piano:** "5 of 9" diventa "n of 10". Il gate `test` mancava dal conto, ed è inseparabile da test-proof (ADR 0053 §4: test-proof prova qualcosa solo dopo `test` verde sulla testa); perimetro e spec chiedono un ticket. Su un repository senza ticket di lights-out il default è quindi **2 gate** (risk, test-weakening, nessun codice del repository eseguito), 4 con `TICKET=`, 6 con anche `TEST_ON_HOST=1` (test e test-proof sull'host, in checkout usa e getta fuori dal repository). La riga: `GO: gates-light — risk <level>, <decision>; <n> of 10 gates ran; secrets, deps, sast, mutation need the image[; test, test-proof need TEST_ON_HOST=1][; perimeter, spec need TICKET=]`, mai `GO: gates`. `./go ci` verde in un clone sotto `.crew/` (4:35, `GO: gates-light`, `GO: contract` esteso al nuovo entry point): sulle nove fixture di `demo-gates` il verdetto leggero coincide con `expect` dove entrambi girano (risk e test-weakening; test e test-proof lì non girano, il `TEST_CMD` dell'app vuole il Postgres di compose: sono provati sui repository di prova dei test unitari). Ricette hook `--light`, timeout 30 s: eseguite una volta contro Claude Code 2.1.311, Codex 0.166.0 e Gemini CLI 0.61.0-preview.0 nelle loro immagini, con il modello scriptato: una rimozione di asserzione è bloccata e la riga NO-GO torna al modello, un cambio pulito passa; non coperti il trust di Codex e la cartella non fidata di Gemini. GitHub Actions su 58824ec, sei workflow verdi (ci 42507391349, stranger 42507391336, self 42507391335, site 42507391329, package 42507391379, podman 42507391334): `GO: demo, milestone M9, 847s to rollback` (engine-compat) e 745 s (stranger), contro 834 e 828 s di M33; self `GO: gates — risk high, review, in workbench`. Pubblicare su PyPI è dell'owner (`docs/launch/checklist.md`); il nome `lights-out` era libero il 2026-11-08, non riservato.

### Dopo

M16 (la rete, decisa), M17 e M11 (board e console), i track cloud di M8 e M10: quando esiste un consumatore esterno, come in §14. La sequenza dopo M35 (attestazione, giuria, loop chiuso, toolbelt, stack) è nella roadmap di adozione, §7.

*Emendamento 2026-11-04 (ADR 0047, proposta):* M11 si costruisce **dopo il merge di M22**, mai prima: il post mortem è una delle cinque schermate e la sua forma (ADR 0044) deve essere ferma. Precondizioni dentro M11, prima delle schermate: i campi di costo di `run.json` nel documento della tower (con le chiavi di M19) e il log dei rilasci `.crew/releases.jsonl`. M21 non è una precondizione: cambia solo `pr.url` e `CODE_HOST`, che il logbook passa così come sono; la raccomandazione è comunque M11 dopo M21, perché un cliente vuole i link al suo GitHub. Il posto di M11 dopo l'esperimento resta, a meno che un design partner lo chieda prima. Le decisioni aperte per l'owner sono in fondo ad ADR 0047.

*Nota 2026-11-07 (studio dell'owner).* Con M24: il `test-reviewer` su un fornitore diverso da quello del `dev-worker` per rischio medio e alto, se la seconda chiave c'è, altrimenti il default resta un fornitore solo; un eval del `test-reviewer` su diff etichettati, per fornitore. Dopo M24, ognuno con la sua ADR: un gate sulla spec del ticket e un passo in cui `product` fa domande prima di `assign`; la coda di merge è diventata M30 senza coda (decisione dell'owner, stesso giorno). La mappa del progetto è diventata M28 (decisione dell'owner, stesso giorno): un file ricostruito a ogni merge, misurato dentro M24. Scartati: un database a grafo come servizio del piano, al posto di quel file (regola d'oro), un ruolo integratore (i ruoli sono sei: un conflitto torna al `dev-worker` come rework, ADR 0038) e l'editor delle spec dentro questo repository (ADR 0029 §3).

### Rischi di questo arco

- **Tre CLI che cambiano in fretta.** Ogni harness è pinnato e ha la sua suite di conformità in `./go ci`; un bump è un commit a sé con la suite come eval, come per Gemini CLI (ADR 0018).
- **La regola d'oro con tre fornitori.** L0 replaya e non chiama nessuno; le fixture registrano chi ha risposto. Nessuna fixture viene scritta a mano per un harness nuovo: o si registra, o il demo di quell'harness non esiste.
- **La guardia senza hook.** Dove la CLI non ha hook, la guardia è il contenitore; la suite di conformità lo prova e il README lo dichiara. Mai "equivalente" senza la prova.
- **Il costo.** Claude e OpenAI non hanno free tier: il README dà il costo misurato di un run per fornitore prima del lancio, dai `run.json` registrati.
