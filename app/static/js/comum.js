// Utilidades compartilhadas pelas páginas (sem framework, sem dependências).
'use strict';

const $ = (id) => document.getElementById(id);

const Comum = {
    formatarReais(centavos) {
        return `R$ ${Math.floor(centavos / 100)},${String(centavos % 100).padStart(2, '0')}`;
    },

    /** Preço (em centavos) da menor faixa que comporta a quantidade. */
    precoPara(quantidade, faixas) {
        const faixa = faixas.find(f => quantidade <= f.ate) || faixas[faixas.length - 1];
        return faixa.centavos;
    },

    // Pedidos lembrados neste navegador (últimos 5), para retomar depois
    lerPedidos() {
        try {
            return JSON.parse(localStorage.getItem('meusPedidos') || '[]');
        } catch (e) {
            return [];
        }
    },

    lembrarPedido(pedido) {
        try {
            const lista = Comum.lerPedidos().filter(p => p.token !== pedido.token);
            lista.unshift({ token: pedido.token, nome_deck: pedido.nome_deck, criado_em: pedido.criado_em });
            localStorage.setItem('meusPedidos', JSON.stringify(lista.slice(0, 5)));
        } catch (e) { /* armazenamento indisponível: o link do pedido continua valendo */ }
    },

    guardarPedidos(lista) {
        try {
            localStorage.setItem('meusPedidos', JSON.stringify(lista));
        } catch (e) { /* ignora */ }
    },

    async copiar(texto, campoReserva) {
        try {
            await navigator.clipboard.writeText(texto);
        } catch (e) {
            if (campoReserva) {
                campoReserva.select();
                document.execCommand('copy');
            }
        }
    },

    /** Card que vira ao clicar/tocar (ou Enter/espaço), acessível por leitor de tela. */
    criarFlashcard(pergunta, resposta) {
        const botao = document.createElement('button');
        botao.type = 'button';
        botao.className = 'flashcard';
        botao.setAttribute('aria-pressed', 'false');

        const faces = document.createElement('span');
        faces.className = 'faces';

        const frente = Comum._face('frente', 'Pergunta', pergunta, 'Toque para ver a resposta');
        const verso = Comum._face('verso', 'Resposta', resposta, 'Toque para voltar à pergunta');
        verso.setAttribute('aria-hidden', 'true');
        faces.append(frente, verso);
        botao.append(faces);

        botao.addEventListener('click', () => {
            const virado = botao.classList.toggle('virado');
            botao.setAttribute('aria-pressed', String(virado));
            frente.setAttribute('aria-hidden', String(virado));
            verso.setAttribute('aria-hidden', String(!virado));
        });
        return botao;
    },

    _face(classe, etiqueta, texto, acao) {
        const face = document.createElement('span');
        face.className = `face ${classe}`;
        const rotulo = document.createElement('span');
        rotulo.className = 'etiqueta';
        rotulo.textContent = etiqueta;
        const conteudo = document.createElement('span');
        conteudo.textContent = texto;
        const dica = document.createElement('span');
        dica.className = 'acao';
        dica.textContent = acao;
        face.append(rotulo, conteudo, dica);
        return face;
    },

    esperar(ms) {
        return new Promise(resolver => setTimeout(resolver, ms));
    },
};
