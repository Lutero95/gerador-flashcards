import math
USD=5.20*1.035   # dolar comercial 28/09/2026 + IOF 3,5% no cartao internacional
PIX=0.0099
MODELOS={ # (in, out) US$/1M
 "Gemini 3.1 Flash-Lite":(0.25,1.50),
 "Gemini 3.5 Flash-Lite":(0.30,2.50),
 "GPT-5.6 Luna":(0.20,1.20),
 "Gemini 3 Flash":(0.50,3.00),
 "Gemini 3.8 Flash (promo)":(0.75,3.75),
 "Gemini 3.8 Flash (pos-promo)":(1.50,7.50),
 "Claude Haiku 4.5":(1.00,5.00),
 "Claude Sonnet 5":(2.00,10.00),
 "Gemini 3.1 Pro":(2.00,12.00),
 "GPT-5.6 Terra":(2.00,12.00),
}
PERFIS={"Idiomas":50,"Escola/ENEM":75,"Graduacao":95,"Programacao":95,"Medicina":110,"Concurseiro":140}
FAIXAS=[(50,3.90),(100,6.90),(200,9.90),(500,18.90),(1000,27.90),(2000,39.90)]
LOTE=40; BASE_IN=1500; DEDUP_TOK=20; DEDUP_MAX=200
def preco(n):
    for lim,p in FAIXAS:
        if n<=lim: return p
    return 39.90
def custo(n, modelo, tpc, thinking=0.0, material=0, retry=0.10, verificar=None):
    pin,pout=MODELOS[modelo]
    lotes=math.ceil(n/LOTE); tin=tout=0
    tin+=2000+material; tout+=800*(1+thinking)          # plano
    for i in range(lotes):
        ja=min(i*LOTE,DEDUP_MAX)
        tin+=BASE_IN+material+ja*DEDUP_TOK
        tout+=min(LOTE,n-i*LOTE)*tpc*(1+thinking)
    usd=(tin*pin+tout*pout)/1e6*(1+retry)
    if verificar:
        vi,vo=MODELOS[verificar]
        usd+=(n*tpc+1000)*vi/1e6 + n*10*vo/1e6
    return usd*USD
def margem(n,**k):
    rec=preco(n)*(1-PIX); c=custo(n,**k); return rec-c, c, rec
if __name__=="__main__":
    import sys
    for cen,kw in [("A) Tema digitado, thinking DESLIGADO",dict(thinking=0)),
                   ("B) Tema digitado, thinking SEM CONTROLE (~2x a saida)",dict(thinking=1.0)),
                   ("C) PDF de 30 pag. reenviado a cada lote, thinking desligado",dict(thinking=0,material=18000))]:
        print("\n###",cen,"— perfil Concurseiro (140 tok/card). Custo R$ / margem % no topo de cada faixa")
        print("modelo".ljust(30)+"".join(f"{n:>13}" for n,_ in FAIXAS))
        for m in MODELOS:
            row=m.ljust(30)
            for n,_ in FAIXAS:
                l,c,r=margem(n,modelo=m,tpc=140,**kw); row+=f"{c:6.2f}|{100*l/r:4.0f}%".rjust(13)
            print(row)
