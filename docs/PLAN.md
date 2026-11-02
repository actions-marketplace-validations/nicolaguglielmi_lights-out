# lights-out — implementation plan

Piano da consegnare a Claude Code per costruire la versione Google-based della piattaforma di sviluppo agentico. Il repo ha due pubblici: chi lo clona dopo un talk e lo fa girare sul portatile, e chi lo porta su un progetto GCP vero.

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
| Git e PR | Gitea in compose | Gitea | GitHub reale (adapter a M10) | GitHub reale |
| CI | Gitea Actions (act runner) | Gitea Actions | GitHub Actions o Cloud Build | idem |
| Registry e firma | Zot locale, firma con chiave locale, verifica della firma nel launchpad prima dello staging | idem | Artifact Registry, firma con chiave KMS, verifica con la stessa cosign, Binary Authorization come seconda serratura | idem |
| Canary | Envoy weighted cluster | Envoy | Cloud Deploy → Cloud Run | + opzione GKE |
| Database dell'app | Postgres in compose | idem | Cloud SQL — **non scala a zero, unico costo fisso**: si ferma o si cancella fra un test e l'altro | idem |
| Metriche | Prometheus | Prometheus | Managed Prometheus + Cloud Monitoring | idem |
| Grafici della console | Grafana | Grafana | Cloud Monitoring | idem |
| Flag | flagd (file) | flagd | flagd su Cloud Run (file su GCS) o Unleash | idem |
| Eventi e stato | Pub/Sub emulator + Firestore emulator | idem | Pub/Sub + Firestore (adapter a M10) | + adapter Cloud Workflows |
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

---

## 4. Porte e adapter

Il nucleo non conosce nessun fornitore. Ogni integrazione sta dietro un'interfaccia con almeno due implementazioni, e la scelta avviene da variabile d'ambiente del profilo — eccetto `Workload`, scelto da `WORKLOAD=<path>` (default `app`), lo stesso a ogni livello (ADR 0030 §1).

| Porta | Adapter | Note |
|---|---|---|
| `AgentHarness` | `replay`, `gemini-cli`, `antigravity-sdk`, `adk` | esegue un ruolo su un workspace e restituisce artefatti |
| `CodeHost` | `gitea`, `github` | branch, PR, commenti, merge, stato di un commit e attesa di quello stato (`await.sh`, ADR 0025 §5) |
| `Tracker` | `file`, `github-issues`, `linear` | il ticket è la sorgente del lavoro |
| `EventBus` | `pubsub-emulator`, `pubsub` | stesso codice, cambia l'endpoint |
| `StateStore` | `firestore-emulator`, `firestore` | stato del workflow, idempotenza |
| `Orchestrator` | `inproc`, `cloud-workflows` | macchina a stati del ciclo di vita del ticket |
| `Delivery` | `envoy-canary`, `cloud-deploy` | quattro verbi: `deploy.sh <version> <image>`, `shift.sh <pct>`, `rollback.sh`, `status.sh`; **plugin**: si carica da `DELIVERY=` nel profilo, aggiungerne uno = una cartella + una riga, zero modifiche a `core/` (ADR 0024); ogni adapter passa la suite di conformità `gates/delivery-conformance.sh` (ADR 0026) |
| `Metrics` | `prometheus`, `managed-prometheus` | stessa query PromQL |
| `Flags` | `flagd`, `unleash` | OpenFeature, l'SDK non cambia; due verbi per il nucleo e i target: `evaluate.sh <flag> [version]`, `set.sh <flag> <variant>` (ADR 0026 §3) |
| `Registry` | `zot`, `artifact-registry` | `publish.sh <tag>` costruisce, firma e pusha stampando il riferimento immutabile; `verify.sh <tag>` verifica la firma e stampa il digest verificato (ADR 0025 §1) |
| `Charts` | `grafana`, `cloud-monitoring` | i grafici che la console mostra; la console non li ridisegna (ADR 0023) |
| `Workload` | `app`, `workloads/minimal` | ciò su cui la piattaforma opera, scelto da `WORKLOAD=<dir>` (default `app`), non dal profilo; `workload.env`, `compose.yaml`, `/healthz` e `/metrics` su `:8000`, `flags/flags.json`, `smoke.sh`, `load.sh`, runner in-image test/mutation/SAST, `fixtures/gates/`; non nominato in `core/`, `gates/`, `verify/`, `adapters/` (`ci/app-free.sh`); verificato da `ci/workloads.sh` e `./go demo-seam` (ADR 0030) |

Regola: **un adapter non può introdurre concetti nuovi nel nucleo.** Se Cloud Deploy ha un concetto che Envoy non ha, o lo si modella in astratto o resta dentro l'adapter.

*Emendamento 2026-09-20 (ADR 0024):* la regola è provata, non solo dichiarata. `ci/vendor-free.sh` fallisce se un file di `core/` nomina un fornitore di Delivery (Envoy, Cloud Deploy, Argo), anche in un commento. Il contratto di un adapter Delivery è la suite di conformità: promuove (staging → 5% → 25% → 100%), boccia e torna indietro su verify NO-GO, rispetta il freeze, riporta lo stato (`status.sh`: versione stabile, versione canary, peso). `envoy-canary` la passa oggi; `cloud-deploy` la passa come criterio di M8; è il requisito d'ingresso per qualunque adapter futuro. Il motore di container resta una scelta dell'utente, non un adapter: podman è il riferimento, docker è supportato e provato da `./go engine-compat` (ADR 0004, ADR 0012 §4).

*Emendamento 2026-09-20 (ADR 0026):* `ready.sh` **non è un verbo della porta `Delivery`**: è la sonda di readiness che ogni adapter presente in `PLANE_ADAPTERS` deve a `make up`, qualunque sia la sua porta (ADR 0012 §6). La suite di conformità non la chiama mai. `status.sh` stampa un solo oggetto JSON con esattamente tre chiavi — `stable` (stringa), `canary` (stringa o `null`), `weight` (intero 0–100) — e niente altro: quello che un fornitore vuole aggiungere va su stderr. La lista di parole di `ci/vendor-free.sh` cresce con `flagd|unleash`, perché il freeze esce da `core/launchpad.sh` e passa dietro la porta `Flags`.

---

## 5. Decisioni già prese

### Chi scrive il codice
**`gemini-3.8-flash`** tramite **Gemini CLI in headless** (`gemini -p "..." --output-format json`), eseguito dentro un container per ogni task. Gemini CLI è Apache 2.0, ha `GEMINI.md` per le istruzioni di progetto, extension, skill, hook, custom command e client MCP: è l'equivalente dell'harness che serve, ed è l'unico clonabile da uno sconosciuto.

**Attenzione, cambiato da poco:** dal 18 giugno 2026 Google non serve più le richieste di Gemini CLI per Gemini Code Assist individuale, Google AI Pro e Ultra, e ha rimosso il "Login with Google" personale, indirizzando gli individui su Antigravity CLI. Quindi il percorso documentato per chi clona è **Gemini API key** (free tier intorno a 250 richieste al giorno, solo modelli Flash) oppure Vertex AI. Il README deve dirlo in modo esplicito, altrimenti il primo che prova si blocca sull'autenticazione e scrive una issue.

**Un solo modello per tutti i ruoli, la leva è il thinking level.** Gemini 3.8 Flash (2 settembre 2026) è il modello Flash più capace, pensato per software engineering a lungo orizzonte e agenti autonomi, con finestra da 1M token e tre livelli di thinking. Consuma di proposito più token sui task lunghi, perché fa passi di ragionamento più piccoli, chiama i tool in modo iterativo e verifica il lavoro; per i task ordinari si abbassa lo sforzo di ragionamento.

Quindi `thinking` diventa un campo della definizione del ruolo, accanto a budget di token, timeout e iterazioni massime:

| Ruolo | thinking | perché |
|---|---|---|
| dev worker | high | task lungo, molti tool, va verificato |
| test e review | high | deve trovare quello che l'autore non ha visto |
| architect | high | poche chiamate, alto impatto |
| product | medium | conversazione, non esecuzione |
| release brief | low | formatta dati che ha già |
| ops triage | low | volumi alti, latenza conta, è il caso d'uso citato per le pipeline di incident response |

Conseguenza operativa: a L1 il free tier limita ai modelli Flash e a un tetto giornaliero di richieste, che con 3.8 Flash basta se i task del demo restano piccoli e il thinking resta basso. La demo dal palco gira a L2, dove alzi il thinking e non hai il tetto.

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

### Antigravity
Antigravity 2.0 (I/O 2026) è una piattaforma su cinque superfici: app desktop, CLI, SDK Python sull'harness degli agenti, Managed Agents nella Gemini API (fatturati per run, non per token) ed Enterprise Agent Platform. Dove lo usiamo:

- **Superficie umana**: il Manager per orchestrare e osservare gli agenti mentre lavorano, con il repo aperto. È quello che mostri sul palco quando fai vedere i worker in parallelo.
- **Adapter opzionale** `antigravity-sdk` per l'harness, dietro la stessa porta di Gemini CLI, così il confronto tra i due è una variabile d'ambiente e diventa una slide.
- **Non** come control plane e **non** nel percorso critico del repo clonabile: è in public preview, i limiti del piano gratuito sono già stati tagliati una volta, la CLI su Linux è indicata come preview e i Managed Agents si pagano a run. Va bene per la demo, non per la riproducibilità.

### Stitch
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

### M12 — Il seam: l'app dietro una porta
L'app bersaglio smette di essere cablata nella piattaforma. Una porta per il workload (nome e contratto in ADR 0030) con un file d'istanza che dichiara tutto ciò che gate, launchpad, verify e tower devono sapere dell'app: path del package, lockfile, comando di test, target di mutation, endpoint delle metriche, flag del kill switch, servizi compose. `ci/app-free.sh` fallisce se `core/`, `gates/`, `verify/` o `adapters/` nominano l'app, come `ci/vendor-free.sh` fa per i fornitori di Delivery. Un secondo workload, deliberatamente minimo, dimostra che il seam è reale e non solo dichiarato. Zero ruoli nuovi, zero modelli nuovi, nessuna capacità visibile in più: è la milestone che rende possibili tutte le altre.
**Fatto quando:** `./go ci` è verde con il nuovo check `app-free`; `./go demo` a L0 stampa lo stesso `GO: demo` di M9, entro lo stesso budget di 900 s, con le stesse fixture e gli stessi ticket; e il secondo workload arriva al rollback automatico e passa i gate su una fixture committata, con un comando fuori dalla lista fissa di `./go demo` (ADR 0003), la cui forma è fissata in ADR 0030.

*Nota 2026-09-23 (chiusura M12):* closed. Acceptance, all on a rebuilt workbench (`./go clean`) and a clean plane: `./go demo` → `GO: demo, milestone M9, 525s to rollback (budget 900s, plan §2)`, 26 ci checks GO including `workloads` and `app-free`, rollback on `error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=0.000`; `./go demo-seam` → `GO: demo-seam`, rollback on `error_rate canary(0.2.0-outage)=1.000 stable(0.1.0-minimal)=0.000`, its own `honest-fix` fixture GO; `docker-compose config` of the merged app project byte-identical to the pre-M12 capture. The live runs happened on `APP_PORT=9000`: on the dev machine host port 8080 was held by another project's container, so the edge's host port became a knob (Makefile and compose, default 8080, `.env.example` and README say so) instead of stopping it — the likeliest way `./go demo` fails for a cloner, now with a one-line fix. The `.env` parking pre-step was wrong: gitleaks' working-tree scan ignores `.gitignore`, so the key must leave the repo directory, not be renamed inside it. What M12 left unproven, and the §14 experiment needs first: a workload in its own repository (`adapters/gitea/bootstrap.sh` pushes this checkout), a worker toolchain beyond Python and Node, a workload-neutral dev-worker prompt, and an envoy-canary probe without `python3`.

### M13 — Pronti per l'esperimento: prompt neutro e report
*Aggiunta 2026-09-23, decisione dell'owner.* La milestone piccola in main che l'esperimento del §14 presuppone. Tre cose, nessuna capacità dell'harness cambia:
- **Il prompt del dev-worker diventa neutro rispetto al workload.** `roles/dev-worker/prompt.md` oggi fissa `app/backend/`, `uv sync` e `pytest` (righe 15–31); ciò che è specifico dell'app (dove sta il codice, come si lanciano i test) passa in un file del workload che il worker legge. Le fixture 0001 e 0005 si ri-registrano a L1 sul prompt nuovo, così L0 continua a replayare ciò che L1 ha prodotto. `ci/app-free.sh` estende il suo scope a `roles/`.
- **`./go report`**: il resoconto di un lotto di ticket, generato dai dati che la piattaforma ha già (documenti della tower, verdetti dei gate, `run.json` del harness, release record, `./go audit`), senza stato proprio (la regola della console, ADR 0023). Per ticket: esito, PR, perimetro, verdetto di ogni gate con mutation score contro il baseline, review con motivo, tentativi/token/tool call/durata, canary. In testa: il criterio di uscita, il costo totale e per ticket, i fallimenti per causa. Markdown; HTML se serve da mostrare. È il deliverable di ogni engagement, non solo il case study: per la regola di confine sta qui.
- **I documenti della tower sopravvivono a un `./go down`.** Oggi stanno nell'emulatore Firestore senza volume; un esperimento che dura giorni li perderebbe. Il come (volume, export prima del `down`) è dell'ADR.
Prima di scrivere: un ADR corto per il report e la persistenza.
**Fatto quando:** `./go ci` verde con `app-free` esteso a `roles/`; `./go demo` identico entro il budget, con le fixture 0001/0005 ri-registrate (`input_matches_recorded: true`); `./go report` su `./go e2e` produce il resoconto del ticket 0001 con numeri che coincidono con quelli di `./go audit`; e dopo `./go down` + `./go up` il report si rigenera identico.

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
- Non aggiungere un settimo ruolo senza togliere qualcosa: il titolo del talk dice sei.
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
