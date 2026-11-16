// Página do pedido: prévia, pagamento via Pix, geração em lotes e downloads.
'use strict';

(() => {
    const TOKEN = $('conteudo').dataset.token;
    const URL_API = `/api/pedidos/${encodeURIComponent(TOKEN)}`;
    const ANTES_DO_PAGAMENTO = ['previa_pronta', 'aguardando_pagamento', 'expirado'];
    const MUDA_SOZINHO = ['aguardando_pagamento', 'pago', 'gerando'];  // estados que pedem polling
    const CLASSE_SELO = {
        concluido: 'ok', pago: 'ok', gerando: 'ok',
        expirado: 'alerta', aguardando_pagamento: 'alerta',
        falhou: 'erro', reembolsado: 'erro',
    };

    let estado = null;
    let polling = null;
    let relogio = null;
    let rodandoLotes = false;
    let baixouAutomaticamente = false;

    function mostrarErro(texto) {
        $('mensagem').textContent = texto;
        $('mensagem').hidden = false;
    }

    function limparErro() {
        $('mensagem').hidden = true;
    }

    // Stepper: 1 Descreva → 2 Prévia → 3 Pague e baixe

    function desenharPassos(dados) {
        const naPrevia = ['previa_pronta', 'expirado'].includes(dados.status) && !dados.pix;
        const passos = [...$('passos').children];
        const atual = naPrevia ? 1 : 2;
        passos.forEach((passo, indice) => {
            passo.classList.toggle('feito', indice < atual || dados.status === 'concluido');
            passo.classList.toggle('atual', indice === atual && dados.status !== 'concluido');
            if (indice === atual) passo.setAttribute('aria-current', 'step'); else passo.removeAttribute('aria-current');
        });
    }

    // Pix

    function atualizarContador() {
        if (!estado || !estado.pix || !estado.pix.expira_em) {
            $('contador').textContent = '';
            return;
        }
        const restante = Math.floor((new Date(estado.pix.expira_em) - Date.now()) / 1000);
        if (restante <= 0) {
            $('contador').textContent = 'Código expirado. Gere um novo.';
            clearInterval(relogio);
            relogio = null;
            carregar();
            return;
        }
        const minutos = String(Math.floor(restante / 60)).padStart(2, '0');
        const segundos = String(restante % 60).padStart(2, '0');
        $('contador').textContent = `O código expira em ${minutos}:${segundos}`;
    }

    // Desenho da página a partir do estado vindo da API

    function desenhar(dados) {
        const anterior = estado;
        estado = dados;
        Comum.lembrarPedido(dados);
        $('carregandoPedido').hidden = true;
        $('conteudoPedido').hidden = false;
        desenharPassos(dados);

        $('nomeDeck').textContent = dados.nome_deck || 'Seu baralho';
        $('resumo').textContent = `${dados.quantidade_solicitada} flashcards · ${dados.preco_texto} · ${dados.assunto}`;
        $('selo').textContent = dados.status_texto;
        $('selo').className = `selo ${CLASSE_SELO[dados.status] || ''}`;
        $('avisoIa').textContent = dados.aviso_ia || '';

        // Prévia (só antes do pagamento)
        const mostrarPrevia = dados.previa.length > 0 && ANTES_DO_PAGAMENTO.includes(dados.status);
        $('secaoPrevia').hidden = !mostrarPrevia;
        $('colunas').classList.toggle('duas-colunas', mostrarPrevia);
        $('colunas').classList.toggle('pagando', Boolean(dados.pix));
        if (mostrarPrevia && $('listaPrevia').childElementCount !== dados.previa.length) {
            $('listaPrevia').replaceChildren(...dados.previa.map(c => Comum.criarFlashcard(c.pergunta, c.resposta)));
        }
        $('blocoSubtopicos').hidden = !dados.subtopicos.length;
        $('listaSubtopicos').replaceChildren(...dados.subtopicos.map(sub => {
            const item = document.createElement('li');
            item.textContent = `${sub.nome} (${sub.quantidade} cards)`;
            return item;
        }));

        // Compra: e-mail + gerar Pix
        $('secaoCompra').hidden = !dados.pode_gerar_pix;
        if (dados.pode_gerar_pix) {
            $('tituloCompra').textContent = dados.status === 'expirado' ? 'O código Pix expirou'
                : dados.previa.length ? 'Gostou? Gere o baralho completo' : 'Gere o baralho completo';
            $('totalCompra').textContent = `Baralho completo com ${dados.quantidade_solicitada} cards`;
            $('precoCompra').textContent = dados.preco_texto;
            $('gerarPix').textContent = dados.status === 'expirado' ? 'Gerar novo código Pix' : `Pagar ${dados.preco_texto} com Pix`;
            if (dados.email && !$('email').value) $('email').value = dados.email;
        }

        // Pix vigente
        $('secaoPix').hidden = !dados.pix;
        if (dados.pix) {
            $('qrCode').hidden = !dados.pix.qr_code_base64;
            if (dados.pix.qr_code_base64) $('qrCode').src = `data:image/png;base64,${dados.pix.qr_code_base64}`;
            $('codigoPix').value = dados.pix.qr_code || '';
            $('painelTeste').hidden = !(dados.modo_teste && dados.pix.id_teste);
            if (!relogio) relogio = setInterval(atualizarContador, 1000);
            atualizarContador();
        } else if (relogio) {
            clearInterval(relogio);
            relogio = null;
        }

        // Geração em lotes
        const gerando = ['pago', 'gerando'].includes(dados.status);
        $('secaoGeracao').hidden = !gerando;
        if (gerando) {
            const feitos = Math.min(dados.quantidade_gerada, dados.quantidade_solicitada);
            const porcentagem = Math.round(100 * feitos / dados.quantidade_solicitada);
            $('barraPreenchida').style.width = `${porcentagem}%`;
            $('barra').setAttribute('aria-valuenow', String(porcentagem));
            $('progressoTexto').textContent = `${feitos} de ${dados.quantidade_solicitada} cards prontos`;
            const lote = dados.lote_atual;
            $('etapaTexto').textContent = lote
                ? `Parte ${lote.posicao} de ${lote.total}: ${lote.subtopicos.join(', ')}`
                : 'Preparando a geração...';
        }

        // Falha após o pagamento: o cliente escolhe como resolver
        $('secaoResolucao').hidden = !dados.resolucao;
        if (dados.resolucao) {
            const parcial = dados.resolucao.parcial;
            $('resolucaoTexto').textContent = parcial
                ? `A IA gerou ${parcial.cards} de ${dados.quantidade_solicitada} cards. Escolha como prefere seguir:`
                : 'Escolha como prefere seguir:';
            $('resolverParcial').hidden = !parcial;
            if (parcial) $('resolverParcial').textContent = `Ficar com os ${parcial.cards} cards e receber ${parcial.reembolso_texto} de volta`;
            $('resolverTotal').textContent = `Receber o reembolso total (${dados.resolucao.total.reembolso_texto})`;
        }
        $('reembolsoInfo').hidden = !dados.reembolso_texto;
        if (dados.reembolso_texto) {
            $('reembolsoInfo').textContent = `Reembolso de ${dados.reembolso_texto} solicitado; o valor volta pelo mesmo Pix.`;
        }

        // Conclusão: download automático na primeira vez que o baralho fica pronto nesta página
        $('secaoConcluido').hidden = !dados.downloads;
        if (dados.downloads) {
            $('baixarApkg').href = dados.downloads.apkg;
            $('baixarPdf').href = dados.downloads.pdf;
            $('resumoFinal').textContent = `${dados.quantidade_gerada} flashcards sobre ${dados.assunto}.`;
            $('disponivelAte').textContent = dados.disponivel_ate
                ? `Disponível para download até ${new Date(dados.disponivel_ate).toLocaleDateString('pt-BR')}.` : '';
            const acabouDeConcluir = anterior && ['pago', 'gerando'].includes(anterior.status);
            if (acabouDeConcluir && !baixouAutomaticamente) {
                baixouAutomaticamente = true;
                $('resumoFinal').textContent += ' O download começou; se não começar, use o botão abaixo.';
                $('baixarApkg').click();
                $('tituloConcluido').focus();
            }
        }

        if (dados.proximo_lote) executarLotes();

        // Polling só enquanto algo pode mudar sozinho
        if (MUDA_SOZINHO.includes(dados.status) && !polling) {
            polling = setInterval(carregar, 5000);
        } else if (!MUDA_SOZINHO.includes(dados.status) && polling) {
            clearInterval(polling);
            polling = null;
        }
    }

    async function carregar() {
        try {
            const resposta = await fetch(URL_API);
            const dados = await resposta.json();
            if (!resposta.ok) {
                mostrarErro(dados.erro || 'Não foi possível carregar o pedido.');
                return;
            }
            desenhar(dados);
        } catch (e) {
            mostrarErro('Sem conexão com o servidor. Tentaremos de novo em instantes.');
        }
    }

    // O navegador pede um lote por vez: cabe no tempo de uma requisição e mostra progresso real

    async function executarLotes() {
        if (rodandoLotes) return;
        rodandoLotes = true;
        try {
            while (estado && estado.proximo_lote) {
                let resposta;
                try {
                    resposta = await fetch(`${URL_API}/lotes/${estado.proximo_lote}`, { method: 'POST' });
                } catch (e) {
                    await Comum.esperar(5000);  // sem conexão: tenta de novo
                    continue;
                }
                const dados = await resposta.json().catch(() => null);
                // Com rodandoLotes ligado, a chamada de executarLotes() dentro de desenhar() não abre outro laço
                if (dados && dados.token) desenhar(dados);
                if ([409, 429, 502].includes(resposta.status)) {
                    await Comum.esperar(4000);  // outra aba gerando, limite de requisições ou falha temporária da IA
                    await carregar();
                } else if (!resposta.ok) {
                    mostrarErro((dados && dados.erro) || 'Não foi possível continuar a geração.');
                    break;
                }
            }
        } finally {
            rodandoLotes = false;
        }
    }

    // Ações

    $('formPagamento').addEventListener('submit', async (evento) => {
        evento.preventDefault();
        limparErro();
        if (!$('email').checkValidity()) {
            mostrarErro('Informe um e-mail válido.');
            $('email').focus();
            return;
        }
        $('gerarPix').disabled = true;
        try {
            const resposta = await fetch(`${URL_API}/pagamento`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: $('email').value.trim() }),
            });
            const dados = await resposta.json();
            if (resposta.ok) {
                desenhar(dados);
                $('copiarPix').focus();
            } else {
                mostrarErro(dados.erro || 'Não foi possível gerar o código Pix.');
            }
        } catch (e) {
            mostrarErro('Sem conexão com o servidor. Tente novamente.');
        } finally {
            $('gerarPix').disabled = false;
        }
    });

    $('ajustarTema').addEventListener('click', () => {
        try {
            sessionStorage.setItem('ajustarTema', JSON.stringify({
                assunto: estado.assunto, quantidade: estado.quantidade_solicitada,
            }));
        } catch (e) { /* ignora */ }
        window.location.href = '/';
    });

    $('copiarPix').addEventListener('click', async () => {
        await Comum.copiar($('codigoPix').value, $('codigoPix'));
        $('copiarPix').textContent = 'Código copiado! Cole no app do seu banco';
        setTimeout(() => { $('copiarPix').textContent = 'Copiar código Pix'; }, 3000);
    });

    $('copiarLink').addEventListener('click', async () => {
        await Comum.copiar(window.location.href);
        $('copiarLink').textContent = 'Link copiado!';
    });

    async function resolver(opcao) {
        limparErro();
        const resposta = await fetch(`${URL_API}/resolucao`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ opcao }),
        });
        const dados = await resposta.json();
        if (resposta.ok) desenhar(dados); else mostrarErro(dados.erro || 'Não foi possível concluir o reembolso.');
    }
    $('resolverParcial').addEventListener('click', () => resolver('parcial'));
    $('resolverTotal').addEventListener('click', () => resolver('total'));

    document.querySelectorAll('#painelTeste [data-acao]').forEach(botao => {
        botao.addEventListener('click', async () => {
            if (!estado || !estado.pix) return;
            await fetch(`/dev/pagamentos/${encodeURIComponent(estado.pix.id_teste)}/${botao.dataset.acao}`, { method: 'POST' });
            carregar();
        });
    });

    carregar();
})();
