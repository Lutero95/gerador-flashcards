from custo import *
# D) PDF grande (200 pag ~120k tokens) reenviado a cada lote vs. fatiado
print("### D) PDF 200 paginas (~120k tokens), Concurseiro, thinking off")
for m in ["Gemini 3.1 Flash-Lite","Gemini 3.8 Flash (promo)","Gemini 3.1 Pro"]:
    for n in (200,500,2000):
        l,c,r=margem(n,modelo=m,tpc=140,material=120000)
        # fatiado: cada lote recebe so a sua fatia (material/lotes) + plano le tudo 1x
        lotes=math.ceil(n/LOTE)
        c2=custo(n,modelo=m,tpc=140,material=0)+ (120000*MODELOS[m][0]/1e6)*USD*2.1
        print(f"  {m:28s} {n:5d} cards  reenviando: custo R${c:6.2f} margem {100*l/r:5.0f}% | fatiado: custo R${c2:5.2f} margem {100*(r-c2)/r:4.0f}%")

# previa: plano + 5 cards, modelo barato, thinking off
def custo_previa(m="Gemini 3.1 Flash-Lite",tpc=140):
    pin,pout=MODELOS[m]; return ((2000*pin)+(800+5*tpc)*pout)/1e6*USD*1.1
print("\nCusto de uma previa (plano+5 cards): Flash-Lite R$%.4f | 3.8 Flash R$%.4f"%(custo_previa(),custo_previa("Gemini 3.8 Flash (promo)")))

# Politica de roteamento proposta (futuro)
def custo_politica(n,perfil):
    tpc=PERFIS[perfil]
    if perfil in ("Idiomas","Escola/ENEM","Programacao"):
        return custo(n,modelo="Gemini 3.1 Flash-Lite",tpc=tpc)
    if perfil=="Graduacao":
        return custo(n,modelo="Gemini 3 Flash",tpc=tpc,thinking=0.3)
    # Concurseiro/Medicina: precisao alta
    if n<=200:
        return custo(n,modelo="Gemini 3.1 Pro",tpc=tpc,thinking=0.5)
    return custo(n,modelo="Gemini 3.8 Flash (promo)",tpc=tpc,thinking=0.3,verificar="Gemini 3.1 Pro")
print("\n### Politica de roteamento proposta: custo R$ e margem % no topo da faixa")
print("perfil".ljust(14)+"".join(f"{n:>13}" for n,_ in FAIXAS))
for p in PERFIS:
    row=p.ljust(14)
    for n,pr in FAIXAS:
        c=custo_politica(n,p); r=pr*(1-PIX); row+=f"{c:6.2f}|{100*(r-c)/r:4.0f}%".rjust(13)
    print(row)

# Carteira mensal
mix_faixa={50:.35,100:.30,200:.18,500:.12,1000:.04,2000:.01}
mix_perfil={"Concurseiro":.35,"Escola/ENEM":.25,"Graduacao":.20,"Medicina":.10,"Idiomas":.05,"Programacao":.05}
# cliente escolhe ~70% do topo da faixa em media
rec=cus=0
for n,pf in mix_faixa.items():
    for p,pp in mix_perfil.items():
        w=pf*pp; q=int(n*0.7) if n>50 else 35
        rec+=w*preco(n)*(1-PIX); cus+=w*custo_politica(q,p)
print(f"\nTicket medio liquido R${rec:.2f} | custo IA medio por venda R${cus:.2f} | margem de contribuicao R${rec-cus:.2f} ({100*(rec-cus)/rec:.0f}%)")
FIXO=20*5.20*1.035 + 86.05 + 40/12
print(f"Custos fixos/mes ~R${FIXO:.2f} (Vercel Pro US$20 + DAS MEI servicos + dominio)")
cp=custo_previa()
for conv in (0.02,0.05,0.10):
    prev_por_venda=1/conv
    mc=rec-cus-prev_por_venda*cp
    print(f"  conversao previa->compra {conv:.0%}: custo de previas por venda R${prev_por_venda*cp:.2f} -> margem por venda R${mc:.2f} -> ponto de equilibrio {math.ceil(FIXO/mc)} vendas/mes")
