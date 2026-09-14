# lights-out

Piattaforma di sviluppo agentico su stack Google: sei ruoli agente che portano un ticket fino alla produzione, e un solo gate umano prima del 100%.

Il piano completo è in `docs/PLAN.md`. Leggilo prima di lavorare su una milestone. Questo file contiene solo le regole che valgono sempre.

## Regola d'oro

Chi clona il repo deve avere una demo funzionante in meno di 15 minuti, senza account GCP, senza carta di credito. `git clone && ./go demo` deve arrivare fino al rollback automatico di un canary, al livello L0, senza nemmeno una API key.

Questa regola vince su qualunque altra considerazione tecnica. Se una scelta la mette a rischio, fermati e chiedi.

## Non negoziabili

- **Niente mock nascosti.** Se un pezzo è simulato a un livello, il README lo dichiara e il codice fallisce con un messaggio chiaro. Mai una finta implementazione che sembra funzionare.
- **Ogni milestone lascia il repo eseguibile.** Prima di dichiararla chiusa: `./go demo` verde su un container pulito.
- **Nessun segreto nel repo**, nemmeno negli esempi. Solo `.env.example` con valori finti.
- **ADR per ogni scelta strutturale**, in `docs/adr/`, corti, con le alternative scartate e il motivo.
- **I test si scrivono dalla spec, mai dall'implementazione.** Vale anche per i test di questo repo.
- **Verifica prima di scrivere.** Antigravity, Stitch, Gemini CLI, ADK e Cloud Deploy si muovono in fretta. Se un'API non esiste più come descritta nel piano, fermati e segnalalo invece di adattare il piano in silenzio.
- **Toolchain nel container.** Sull'host solo podman, git e una shell POSIX; make non è un prerequisito. L'entrypoint è ./go, mai make diretto nei criteri di accettazione.
- **Header SPDX** solo nei file di ingresso di ogni componente (entrypoint, Makefile, Containerfile, main del componente), non in ogni file.

## Contro la sovra-ingegnerizzazione

- La cosa più piccola che fa passare il criterio di accettazione. Nient'altro.
- Nessuna astrazione nuova senza un ADR che la giustifichi.
- Nessun adapter fuori dalla tabella della sezione 4 del piano.
- Nessun settimo ruolo: il titolo del talk dice sei.
- Prima di aggiungere, guarda se puoi togliere.

## Lingua

`docs/PLAN.md` è in italiano, è il documento di lavoro. **Tutto il resto del repo è in inglese**: README, codice, commenti, commit, ADR, messaggi di errore. Il repo è pubblico e i talk sono anche in inglese.

## Due livelli di modelli, da non confondere

- **Runtime**: i ruoli agente girano su `gemini-3.8-flash`, con `thinking` per ruolo. È configurazione di prodotto, sta in `roles/`.
- **Costruzione**: i modelli Claude che scrivono questo repo stanno nel frontmatter dei subagent in `.claude/agents/`. Non finiscono mai nel codice del prodotto.

## Come si lavora

Una milestone per sessione, con la skill `/milestone`. Plan mode prima, esecuzione dopo. Fra una milestone e l'altra: checkpoint del contesto, `/clear`, sessione nuova.

Subagent disponibili: `architect` per decisioni strutturali e ADR, `gate-writer` per `gates/`, `verify/` e i test, `doc-scribe` per README, docs e commit message.
