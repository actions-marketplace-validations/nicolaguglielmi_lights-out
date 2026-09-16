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

---

## 2. La regola d'oro

**Chi clona il repo deve avere una demo funzionante in meno di 15 minuti, senza account GCP, senza carta di credito, senza chiedere niente a nessuno.**

Questa regola vince su qualunque altra scelta tecnica. In pratica significa:

- `git clone && ./go demo` deve arrivare fino al rollback automatico di un canary. Al livello più basso, senza nemmeno una API key.
- Niente mock nascosti. Se un pezzo è simulato, deve esserlo in modo esplicito e dichiarato nel README con una riga tipo "at L0 the canary is a weighted Envoy split, not Cloud Run revisions".
- Ogni livello superiore aggiunge integrazioni reali senza riscrivere il livello sotto. Gli script dei gate, le query delle metriche e le definizioni dei ruoli sono gli stessi a L0 e a L3.
- Se una dipendenza esterna non è accessibile a uno sconosciuto (Stitch, Antigravity Enterprise, quote a pagamento), quella dipendenza **non può stare nel percorso critico**. Deve produrre un artefatto che viene committato nel repo, così chi clona parte da quell'artefatto.

---

## 3. Livelli di integrazione

Quattro livelli. Ognuno è un profilo (`profiles/l0.env` … `profiles/l3.env`) e un target make. Il README deve avere questa tabella in cima.

| | L0 · Replay | L1 · Local | L2 · Cloud | L3 · Platform |
|---|---|---|---|---|
| Serve | podman rootless (podman machine su macOS) | + Gemini API key | + progetto GCP con billing | + quote Agent Engine |
| Modelli | risposte registrate (fixture) | Gemini API, `gemini-3.8-flash` | Gemini Enterprise Agent Platform (ex Vertex AI), `gemini-3.8-flash` | idem + thinking level per ruolo |
| Harness worker | replay | Gemini CLI headless in container | Gemini CLI su Cloud Run Job | + adapter Antigravity SDK |
| Git e PR | Gitea in compose | Gitea | GitHub reale | GitHub reale |
| CI | Gitea Actions (act runner) | Gitea Actions | GitHub Actions o Cloud Build | idem |
| Registry | Zot locale | Zot | Artifact Registry + Binary Authorization | idem |
| Canary | Envoy weighted cluster | Envoy | Cloud Deploy → Cloud Run | + opzione GKE |
| Metriche | Prometheus | Prometheus | Managed Prometheus + Cloud Monitoring | idem |
| Flag | flagd (file) | flagd | flagd su Cloud Run o Unleash | idem |
| Eventi e stato | Pub/Sub emulator + Firestore emulator | idem | Pub/Sub + Firestore | + adapter Cloud Workflows |
| Agenti ADK | stub | ADK locale (`adk web`) | ADK su Cloud Run | Agent Engine + BigQuery analytics |
| Tempo al primo rollback | < 15 min | < 20 min | ~45 min (terraform apply) | ~90 min |

Due scelte che tengono in piedi la tabella:

- **PromQL ovunque.** L'app espone metriche OTel in formato Prometheus. La query che decide se il canary passa è un file solo, `verify/slo.promql`, e gira identica su Prometheus locale e su Managed Prometheus. È la riga più importante di tutto il progetto: senza, L0 e L2 divergono subito.
- **Gitea Actions usa la sintassi di GitHub Actions.** Gli stessi workflow YAML girano in locale e su GitHub. Se qualcosa non è supportato dal runner locale, va isolato in uno step separato e saltato con una condizione, non duplicato.

---

## 4. Porte e adapter

Il nucleo non conosce nessun fornitore. Ogni integrazione sta dietro un'interfaccia con almeno due implementazioni, e la scelta avviene da variabile d'ambiente del profilo.

| Porta | Adapter | Note |
|---|---|---|
| `AgentHarness` | `replay`, `gemini-cli`, `antigravity-sdk`, `adk` | esegue un ruolo su un workspace e restituisce artefatti |
| `CodeHost` | `gitea`, `github` | branch, PR, commenti, merge |
| `Tracker` | `file`, `github-issues`, `linear` | il ticket è la sorgente del lavoro |
| `EventBus` | `pubsub-emulator`, `pubsub` | stesso codice, cambia l'endpoint |
| `StateStore` | `firestore-emulator`, `firestore` | stato del workflow, idempotenza |
| `Orchestrator` | `inproc`, `cloud-workflows` | macchina a stati del ciclo di vita del ticket |
| `Delivery` | `envoy-canary`, `cloud-deploy` | fasi, promote, rollback |
| `Metrics` | `prometheus`, `managed-prometheus` | stessa query PromQL |
| `Flags` | `flagd`, `unleash` | OpenFeature, l'SDK non cambia |
| `Registry` | `zot`, `artifact-registry` | firma e verifica |

Regola: **un adapter non può introdurre concetti nuovi nel nucleo.** Se Cloud Deploy ha un concetto che Envoy non ha, o lo si modella in astratto o resta dentro l'adapter.

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

### Gli agenti ADK
ADK copre i ruoli che non toccano il repo: product agent (dialogo lungo con il PO, sessioni e memoria), triage agent (volumi alti, un modello Flash basta), release agent (prepara il promotion brief). Motivi concreti: flusso di conferma dei tool per l'human-in-the-loop, possibilità di riavvolgere una sessione, analytics su BigQuery con provenienza delle tool call, e `adk eval` che usiamo come test di regressione degli agenti. A L3 girano su Agent Engine, sotto girano in locale.

Pinnare le versioni: ADK ha due linee di release attive, la 2.x e la 1.x. Scegliere la 2.x, fissare la versione esatta, e far passare `adk eval` prima di ogni bump.

### Il control plane
Resta noioso di proposito: eventi su Pub/Sub, dispatcher, macchina a stati con lo stato su Firestore, worker come job effimeri. Entrambi hanno un emulatore ufficiale, quindi L0 e L2 condividono il codice. Cloud Workflows entra come adapter alternativo a L3, non come base.

### L'app bersaglio
Serve un'applicazione vera su cui gli agenti lavorano. Deve essere abbastanza piccola da leggersi in un'ora e abbastanza vera da avere tutto ciò che rompe: **un backend Python (FastAPI) con Postgres, un frontend React, autenticazione, una migrazione di schema, un endpoint dipendente da un servizio esterno** (così esiste un contract test). Dominio suggerito: gestione iscrizioni a un meetup, che è anche il dominio che conosci meglio e regge bene sul palco.

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
  workbench/                # Containerfile della toolchain
  ci/                       # self-check del repo
  core/                     # nucleo senza fornitori: modello artefatti, macchina a stati, risk scoring
  adapters/                 # una cartella per adapter della tabella §4: codice e config del vendor (anche envoy-canary e cloud-deploy)
  roles/                    # un ruolo = una cartella: GEMINI.md, prompt, tool ammessi, skill, hook
    product/ architect/ dev-worker/ test-reviewer/ release/ ops-triage/
  policy/                   # policy-as-code condivisa: cosa serve per mergiare, promuovere, chi tocca cosa
  gates/                    # script dei gate, containerizzati, identici a L0 e L3
  verify/                   # slo.promql e il verify runner
  tickets/                  # i ticket del progetto, uno per file, la sorgente del lavoro a L0 (Tracker=file)
  design/                   # artefatti Stitch committati: tokens, screens, CONTRACT.md
  app/                      # l'applicazione bersaglio
  infra/                    # terraform per L2 e L3
  fixtures/                 # risposte modello registrate per L0
  e2e/                      # il golden path
  docs/                     # architettura, ADR, guida al talk
```

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

### M8 — GCP (L2)
Terraform per progetto, Artifact Registry, Cloud Run, Cloud Deploy con le fasi canary e il verify job, Cloud Monitoring, Binary Authorization, Workload Identity Federation da GitHub, Secret Manager con credenziali per ruolo.
**Fatto quando:** su un progetto nuovo, `./go up PROFILE=l2` porta dallo zero al primo rollback automatico in meno di un'ora, e i file in `gates/` e `verify/` sono gli stessi di L0, verificato da un test che ne confronta gli hash.

*Nota 2026-09-16 (M6, ADR 0019):* qui arrivano anche la socket del runner di Gitea e il primo job di Gitea Actions (tre condizioni di ADR 0015 §7), la build dell'immagine dal merge commit e il push su Zot.

### M9 — Piattaforma (L3) e self-test notturno
Agent Engine per gli agenti ADK, BigQuery agent analytics, adapter Cloud Workflows, opzione GKE, e un job schedulato che ogni notte esegue il golden path completo su un progetto usa e getta.
**Fatto quando:** il badge del nightly è verde nel README, e una regressione nei prompt lo fa diventare rosso.

### M10 — Design loop e materiale da palco
Il server MCP di Stitch collegato all'agente interattivo, gli artefatti di design committati, `docs/TALK.md` con la sequenza della demo e i video di backup di ogni passaggio.
**Fatto quando:** un cloner senza accesso a Stitch ottiene comunque la UI corretta dagli artefatti nel repo.

---

## 8. Il golden path

Un unico test end-to-end, che è insieme la demo, il test di regressione della piattaforma e l'eval degli agenti. Gira a ogni livello.

1. Arriva un ticket: "aggiungi la lista d'attesa quando il meetup è pieno".
2. Il product agent verifica i criteri di accettazione e apre una domanda se mancano.
3. Il dev worker implementa nel suo worktree e apre una PR.
4. La CI esegue i gate, il risk scoring dice rischio medio, parte la review agent.
5. Merge, build, immagine firmata, Cloud Deploy o Envoy porta al 5%.
6. Il verify legge le metriche e boccia, perché la feature dietro flag restituisce 5xx quando il flag è acceso.
7. Rollback automatico, incident aperto, ipotesi ordinate.
8. Seconda corsa con il flag spento: passa, arriva al gate umano, promozione al 100%.
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

## 11. Rischi noti

| Rischio | Cosa succede | Mitigazione |
|---|---|---|
| Quota gratuita insufficiente a L1 | il cloner prova, sbatte sui rate limit, molla | task del demo piccoli, L0 come default assoluto, messaggio d'errore che spiega la quota |
| Antigravity o Stitch cambiano | la demo si rompe una settimana prima del talk | entrambi fuori dal percorso critico, artefatti committati, video di backup |
| L0 e L2 divergono | il repo pubblico diventa demo-ware | test che confronta gli hash di `gates/` e `verify/` tra i profili, nightly su L2 |
| Costo del nightly | fattura a sorpresa | progetto usa e getta, budget alert, scale to zero, Flash sui ruoli non critici |
| Il repo diventa enorme | nessuno lo legge | l'app bersaglio resta piccola, se cresce si taglia |
| docker è uno shim di podman | ci-engine-compat passa senza aver testato docker | il gate stampa le due versioni separate e marca lo shim come non testato |

## 12. Cosa non fare

- Non mettere ADK nel percorso di chi scrive codice sul repo: serve un harness con file, shell e git, non un orchestratore di conversazioni.
- Non usare un albero di agenti come control plane di un flusso che dura giorni.
- Non dare credenziali di produzione a un agente, a nessun livello, nemmeno a L0 per comodità.
- Non lasciare che il verify del canary dipenda da un giudizio del modello: la decisione è numerica, il modello arriva dopo per spiegare.
- Non aggiungere un settimo ruolo senza togliere qualcosa: il titolo del talk dice sei.

---

## 13. Prompt di partenza per Claude Code

> Leggi `docs/PLAN.md` e `CLAUDE.md`. Prima di scrivere codice verifica sulla documentazione ufficiale i sette punti della sezione 10 e riportami solo ciò che risulta diverso dal piano. Poi fermati e aspetta.

Da lì in avanti una milestone per sessione, con `/milestone M0`, `/milestone M1` e così via. Fra una milestone e l'altra: checkpoint del contesto, `/clear`, sessione nuova.
