# Prompt — corrigir loop contínuo do pet idle

## Missão

Corrigir o comportamento da animação do pet no TUI do Hermes. O estado `idle`
atualmente repete seus quadros continuamente enquanto o agente permanece parado,
causando ruído visual e fadiga durante sessões longas.

## Repositório principal

Trabalhar em:

`~/.hermes/hermes-agent`

Não trabalhar no atlas nem gerar novas imagens nesta primeira etapa.

## Contexto verificado

- O renderer do TUI está em `ui-tui/src/app/usePet.ts`.
- O hook mantém um índice de quadro e agenda ticks continuamente.
- O backend fornece `frameMs` junto com os quadros em
  `tui_gateway/methods_session.py`.
- O TUI mantém esse valor no cache, mas o loop usa um intervalo fixo.
- A especificação visual existente em
  `~/repos/avatars/gabiru/run/prompts/rows/idle.md` define `idle` como uma
  animação calma e de baixa distração.
- O comportamento do desktop em
  `apps/desktop/src/components/pet/pet-sprite.tsx` é uma implementação separada.
  Não alterá-la nesta primeira etapa, a menos que a investigação prove que a
  mudança precisa ser compartilhada.

## Comportamento desejado

1. Quando o pet entra no estado `idle`:
   - executar no máximo um ciclo da animação `idle`;
   - ao terminar, exibir o primeiro quadro;
   - permanecer no primeiro quadro enquanto o estado continuar `idle`;
   - não reiniciar o ciclo automaticamente.

2. Quando o estado muda de `idle` para `run`, `review`, `waiting` ou outro estado
   ativo:
   - iniciar a animação daquele estado normalmente;
   - manter o loop contínuo enquanto o estado permanecer ativo.

3. Quando o estado ativo retorna para `idle`:
   - resetar o índice;
   - permitir um novo ciclo único de `idle`;
   - depois voltar novamente ao primeiro quadro.

4. Estados transitórios como `wave`, `jump` e `failed` devem conservar o
   comportamento atual controlado pelo estado/flash do agente.

5. Usar a temporização fornecida por `frameMs` quando ela estiver disponível.
   Não manter o intervalo fixo como fonte principal de ritmo.

6. O comportamento deve funcionar nos dois caminhos do TUI:
   - half-block/cells;
   - kitty/out-of-band image transmission.

   Ao finalizar o ciclo `idle`, os dois caminhos devem deixar o primeiro quadro
   visível, sem deixar o último quadro congelado.

## Restrições

- Não regenerar o `spritesheet`.
- Não alterar `~/repos/avatars` nesta etapa.
- Não alterar ou apagar mudanças locais não relacionadas no repo Hermes.
- Não fazer reset, checkout destrutivo ou limpeza geral do repositório.
- Não criar uma nova opção persistente de configuração.
- Não introduzir timers aleatórios na primeira versão.
- Fazer a menor mudança reversível que resolva o problema.
- Preservar a troca de estado, o cache de frames, o cleanup dos timers e o
  comportamento de pet desabilitado.

## Testes obrigatórios

Adicionar testes comportamentais determinísticos para provar:

- `idle` executa um único ciclo e depois permanece no primeiro quadro;
- avançar o relógio além de vários ciclos não reativa `idle`;
- `run` continua repetindo os quadros enquanto permanecer ativo;
- sair de `run` e voltar para `idle` permite exatamente um novo ciclo;
- não ficam timers duplicados após troca de estado;
- o cleanup do hook cancela o agendamento;
- o comportamento funciona independentemente do número real de quadros;
- `frameMs` é respeitado quando o backend o fornece.

Preferir extrair uma pequena política pura de animação se isso tornar os testes
mais simples. Não testar lendo o texto dos arquivos-fonte.

## Verificação

Executar no mínimo:

```bash
cd ~/.hermes/hermes-agent/ui-tui
npm test
npm run typecheck
npm run lint
```

Se houver alteração no backend Python, executar também a suíte específica pelo
runner oficial do projeto:

```bash
cd ~/.hermes/hermes-agent
scripts/run_tests.sh tests/tui_gateway/
```

## Definition of done

A animação `idle` toca uma vez ao entrar no estado e depois fica visualmente
quieta no primeiro quadro; os estados ativos continuam funcionando; não há timer
duplicado; os testes passam; e o relatório final lista os arquivos alterados, os
comandos executados e a evidência observada.
