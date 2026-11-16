// Página inicial: gerador (abas Tema · Arquivo · Colar texto), preço antes de gerar e pedidos recentes.
'use strict';

(() => {
    const principal = $('conteudo');
    const MAX_CARDS = Number(principal.dataset.maxCards);
    const FAIXAS = JSON.parse(principal.dataset.faixas);
    const MAX_ARQUIVOS = 5;
    const EM_ANDAMENTO = ['previa_pronta', 'aguardando_pagamento', 'expirado', 'pago', 'gerando'];

    let tipoAtivo = 'tema';
    let quantidade = 10;
    let arquivos = [];
    let compraDireta = false;

    // Abas acessíveis (padrão WAI-ARIA: setas, Home e End movem entre abas)

    const abas = [...document.querySelectorAll('[role="tab"]')];

    function ativarAba(aba, focar) {
        abas.forEach(outra => {
            const ativa = outra === aba;
            outra.setAttribute('aria-selected', String(ativa));
            outra.tabIndex = ativa ? 0 : -1;
            $(outra.getAttribute('aria-controls')).hidden = !ativa;
        });
        tipoAtivo = aba.dataset.tipo;
        if (focar) aba.focus();
    }

    abas.forEach((aba, indice) => {
        aba.addEventListener('click', () => ativarAba(aba, false));
        aba.addEventListener('keydown', (evento) => {
            const destino = {
                ArrowRight: abas[(indice + 1) % abas.length],
                ArrowLeft: abas[(indice - 1 + abas.length) % abas.length],
                Home: abas[0],
                End: abas[abas.length - 1],
            }[evento.key];
            if (destino) {
                evento.preventDefault();
                ativarAba(destino, true);
            }
        });
    });

    // Arquivos: arrastar e soltar ou escolher

    const area = $('areaArquivos');
    const entrada = $('entradaArquivos');

    function formatarTamanho(bytes) {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
        return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    }

    function desenharArquivos() {
        $('listaArquivos').replaceChildren(...arquivos.map((arquivo, indice) => {
            const item = document.createElement('li');
            const nome = document.createElement('span');
            nome.className = 'nome';
            nome.textContent = arquivo.name;
            const tamanho = document.createElement('span');
            tamanho.className = 'tamanho';
            tamanho.textContent = formatarTamanho(arquivo.size);
            const remover = document.createElement('button');
            remover.type = 'button';
            remover.className = 'link-botao';
            remover.textContent = 'Remover';
            remover.setAttribute('aria-label', `Remover ${arquivo.name}`);
            remover.addEventListener('click', () => {
                arquivos.splice(indice, 1);
                desenharArquivos();
                area.focus();
            });
            item.append(nome, tamanho, remover);
            return item;
        }));
    }

    function adicionarArquivos(lista) {
        for (const arquivo of lista) {
            if (arquivos.length >= MAX_ARQUIVOS) {
                mostrarErro(`Você pode anexar no máximo ${MAX_ARQUIVOS} arquivos.`);
                break;
            }
            if (!arquivos.some(a => a.name === arquivo.name && a.size === arquivo.size)) arquivos.push(arquivo);
        }
        entrada.value = '';
        desenharArquivos();
    }

    area.addEventListener('click', () => entrada.click());
    area.addEventListener('keydown', (evento) => {
        if (evento.key === 'Enter' || evento.key === ' ') {
            evento.preventDefault();
            entrada.click();
        }
    });
    entrada.addEventListener('change', () => adicionarArquivos(entrada.files));
    ['dragenter', 'dragover'].forEach(tipo => area.addEventListener(tipo, (evento) => {
        evento.preventDefault();
        area.classList.add('arrastando');
    }));
    ['dragleave', 'drop'].forEach(tipo => area.addEventListener(tipo, (evento) => {
        evento.preventDefault();
        area.classList.remove('arrastando');
    }));
    area.addEventListener('drop', (evento) => adicionarArquivos(evento.dataTransfer.files));

    // Quantidade: chips alinhados às faixas de preço + campo livre; preço total sempre visível

    const chips = [...document.querySelectorAll('.chip')];

    function definirQuantidade(valor, origem) {
        quantidade = Math.min(Math.max(parseInt(valor, 10) || 0, 0), MAX_CARDS);
        chips.forEach(chip => chip.setAttribute('aria-pressed', String(Number(chip.dataset.quantidade) === quantidade)));
        if (origem !== 'campo') $('quantidadeOutra').value = chips.some(c => Number(c.dataset.quantidade) === quantidade) ? '' : quantidade;
        $('quantidadeTotal').textContent = quantidade || '—';
        $('precoTotal').textContent = quantidade ? Comum.formatarReais(Comum.precoPara(quantidade, FAIXAS)) : '—';
    }

    chips.forEach(chip => chip.addEventListener('click', () => {
        definirQuantidade(chip.dataset.quantidade, 'chip');
        $('quantidadeAviso').textContent = '';
    }));
    $('quantidadeOutra').addEventListener('input', (evento) => {
        definirQuantidade(evento.target.value, 'campo');
        $('quantidadeAviso').textContent = '';
    });

    // "Quero 50 flashcards sobre..." ajusta a quantidade em vez de ser ignorado
    const QUANTIDADE_NO_TEXTO = /\b(\d{1,4})\s*(flashcards?|cards?|cart[õo]es|perguntas|quest[õo]es)\b/i;
    ['assuntoTema', 'assuntoArquivo', 'assuntoTexto'].forEach(id => $(id).addEventListener('input', (evento) => {
        const achado = evento.target.value.match(QUANTIDADE_NO_TEXTO);
        if (!achado) return;
        const pedida = Math.min(Math.max(parseInt(achado[1], 10), 1), MAX_CARDS);
        if (pedida !== quantidade) {
            definirQuantidade(pedida, 'texto');
            $('quantidadeAviso').textContent = `Ajustamos a quantidade para ${pedida} cards.`;
        }
    }));

    // Envio

    function mostrarErro(texto) {
        $('mensagem').textContent = texto;
        $('mensagem').hidden = false;
    }

    function ativarCompraDireta(mensagem) {
        compraDireta = true;
        $('avisoPrevia').textContent = mensagem;
        $('avisoPrevia').hidden = false;
        $('botaoGerar').textContent = 'Gerar o baralho completo (sem prévia)';
        $('carregandoTexto').textContent = 'Preparando seu pedido...';
    }

    function dadosDoFormulario() {
        const campoAssunto = { tema: 'assuntoTema', arquivo: 'assuntoArquivo', texto: 'assuntoTexto' }[tipoAtivo];
        const assunto = $(campoAssunto).value.trim();
        if (!assunto) return { erro: 'Descreva o assunto dos flashcards.', foco: campoAssunto };
        if (tipoAtivo === 'arquivo' && !arquivos.length) return { erro: 'Escolha pelo menos um arquivo.', foco: 'areaArquivos' };
        if (tipoAtivo === 'texto' && !$('textoColado').value.trim()) return { erro: 'Cole o texto que vai virar flashcards.', foco: 'textoColado' };
        if (quantidade < 1) return { erro: `Escolha de 1 a ${MAX_CARDS} flashcards.`, foco: 'quantidadeOutra' };

        const dados = new FormData();
        dados.append('prompt', assunto);
        dados.append('quantidade', quantidade);
        if (tipoAtivo === 'texto') dados.append('texto', $('textoColado').value.trim());
        if (tipoAtivo === 'arquivo') arquivos.forEach((arquivo, i) => dados.append(`arquivo_${i}`, arquivo));
        if (compraDireta) dados.append('modo', 'direto');
        if (window.turnstile) dados.append('turnstile_token', window.turnstile.getResponse() || '');
        return { dados };
    }

    $('formGerador').addEventListener('submit', async (evento) => {
        evento.preventDefault();
        $('mensagem').hidden = true;
        const { dados, erro, foco } = dadosDoFormulario();
        if (erro) {
            mostrarErro(erro);
            $(foco).focus();
            return;
        }

        $('botaoGerar').disabled = true;
        $('carregando').hidden = false;
        try {
            const resposta = await fetch('/api/pedidos', { method: 'POST', body: dados });
            const corpo = await resposta.json();
            if (window.turnstile) window.turnstile.reset();  // o token vale para uma requisição só

            if (resposta.status === 429 && corpo.compra_direta_disponivel) {
                ativarCompraDireta(corpo.erro);
            } else if (resposta.ok) {
                Comum.lembrarPedido(corpo);
                window.location.href = corpo.url_pedido;
                return;
            } else {
                mostrarErro(corpo.erro || 'Não foi possível gerar a prévia.');
            }
        } catch (e) {
            mostrarErro('Sem conexão com o servidor. Tente novamente.');
        }
        $('botaoGerar').disabled = false;
        $('carregando').hidden = true;
    });

    // Prévias grátis esgotadas (cota do visitante ou orçamento do dia): a compra direta continua

    fetch('/api/previa/disponibilidade')
        .then(resposta => resposta.json())
        .then(dados => { if (dados.disponivel === false) ativarCompraDireta(dados.mensagem); })
        .catch(() => {});

    // Pedidos deste navegador, com atalho para os que estão em andamento

    async function mostrarPedidosRecentes() {
        const salvos = Comum.lerPedidos();
        if (!salvos.length) return;
        const resultados = await Promise.all(salvos.map(async (pedido) => {
            try {
                const resposta = await fetch(`/api/pedidos/${encodeURIComponent(pedido.token)}`);
                if (resposta.status === 404) return null;
                return resposta.ok ? await resposta.json() : { ...pedido, status_texto: '' };
            } catch (e) {
                return { ...pedido, status_texto: '' };
            }
        }));
        Comum.guardarPedidos(salvos.filter((p, i) => resultados[i]));
        const validos = resultados.filter(Boolean);
        if (!validos.length) return;

        const andamento = validos.filter(p => EM_ANDAMENTO.includes(p.status)).length;
        $('pedidosTitulo').textContent = andamento
            ? `Você tem ${andamento} pedido${andamento > 1 ? 's' : ''} em andamento — continuar:`
            : 'Seus pedidos recentes:';
        $('listaPedidos').replaceChildren(...validos.map(pedido => {
            const item = document.createElement('li');
            const link = document.createElement('a');
            link.href = `/pedido/${encodeURIComponent(pedido.token)}`;
            link.textContent = pedido.nome_deck || 'Baralho sem nome';
            item.append(link, document.createTextNode(pedido.status_texto ? ` — ${pedido.status_texto}` : ''));
            return item;
        }));
        $('pedidosRecentes').hidden = false;
    }

    // "Ajustar tema" na página do pedido traz o assunto de volta (sem passar pela URL)

    try {
        const ajuste = JSON.parse(sessionStorage.getItem('ajustarTema') || 'null');
        if (ajuste) {
            sessionStorage.removeItem('ajustarTema');
            $('assuntoTema').value = ajuste.assunto || '';
            if (ajuste.quantidade) definirQuantidade(ajuste.quantidade, 'ajuste');
            $('assuntoTema').focus();
        }
    } catch (e) { /* ignora */ }

    // Exemplo de baralho

    const exemplo = $('baralhoExemplo');
    exemplo.replaceChildren(...JSON.parse(exemplo.dataset.cards).map(([p, r]) => Comum.criarFlashcard(p, r)));

    definirQuantidade(quantidade, 'inicio');
    mostrarPedidosRecentes();
})();
