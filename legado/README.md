# Análise Técnica do MBPLOT (MS-DOS)

## 1. Visão Geral do Sistema

O pacote analisa uma suíte de softwares gráficos clássicos do ambiente MS-DOS em modo estendido (32 bits), baseados na extinta biblioteca **DOS/4GW** (Rational Systems) e **GO32** (DJGPP).

- **Extensores de Memória:** `dos4gw.exe`, `GO32.EXE`
- **Core do Executável de Plotagem:** `mbplot.exe`
- **Utilitários e Suporte:** `HP2XX386.EXE` (conversão para HPGL/Vector), `p.exe`, `pminfo.exe`, `wsite.exe`, `wconvert.exe`.

---

## 2. Lógica de Funcionamento Interno

### 2.1 Modos de Operação

1. **Entrada de Dados:**
   O programa aceita funções matemáticas parametrizadas na forma $y = f(x)$ ou curvas paramétricas $(x(t), y(t))$, além de tabelas de pontos discretos provenientes de arquivos de dados.
2. **Transformação de Coordenadas (World to Screen):**
   O programa converte o sistema de coordenadas do usuário (coordenadas de mundo $[X_{min}, X_{max}] \times [Y_{min}, Y_{max}]$) para o espaço de renderização em pixels/raster da tela $[0, W_{tela}] \times [0, H_{tela}]$ através de transformações afins:

   $$X_{screen} = \frac{X_{world} - X_{min}}{X_{max} - X_{min}} \times W_{screen}$$

   $$Y_{screen} = H_{screen} - \left( \frac{Y_{world} - Y_{min}}{Y_{max} - Y_{min}} \times H_{screen} \right)$$

3. **Mapeamento e Escala Automática (Autoscale):**
   Varre a amplitude da função nos intervalos amostrados $x \in [a, b]$ para definir $Y_{min}$ e $Y_{max}$ dinamicamente, evitando sobreposição e clipping fora da viewport.

---

## 3. Expressões Matemáticas e Algoritmos de Plotagem

O `mbplot` utiliza modelos de amostragem uniforme e funções ortogonais/trigonométricas comuns para modelagem de sinais e gráficos de teste:

### A. Senoides com Atenuação Exponencial (Amortecimento)

Utilizado para modelar oscilações e respostas impulsivas em sistemas físicos:
$$f(x) = A \cdot e^{-\alpha x} \cdot \sin(\omega x + \phi)$$

### B. Curvas Paramétricas de Lissajous

Utilizadas em análises de fase e frequência:
$$x(t) = A \sin(a t + \delta)$$
$$y(t) = B \sin(b t)$$

### C. Ajuste e Interpolação de Curvas

Para dados discretos, utiliza interpolação linear ou polinomial por partes (Splines) para manter a continuidade visual das linhas desenhadas na tela rasterizada.

---

## 4. Pipeline de Renderização no DOS

1. **Ativação da PLVGA/VGA:** Alteração do modo de vídeo via interrupção `INT 10h` para modo `13h` ($320 \times 200$, 256 cores) ou modos VESA ($640 \times 480$, etc.).
2. **Renderização de Linhas:** Algoritmo de Linha de Bresenham para rasterização vetorial direta no buffer de vídeo `0xA0000`.
3. **Exportação Plotter/Vetor:** O Utilitário `HP2XX386` converte a saída de comandos de plotagem em instruções vetoriais HPGL (`SP1; PA x,y; PD;`).
