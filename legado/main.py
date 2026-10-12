import numpy as np
import matplotlib.pyplot as plt

class MBPlotSimulator:
    """
    Simulador da lógica de amostragem, transformação de coordenadas 
    e geração de gráficos do sistema clássico MBPLOT.
    """
    def __init__(self, screen_width=800, screen_height=600):
        self.screen_width = screen_width
        self.screen_height = screen_height

    def world_to_screen(self, x_world, y_world, x_min, x_max, y_min, y_max):
        """
        Converte coordenadas de mundo (matemáticas) para coordenadas de tela (pixels).
        """
        x_screen = ((x_world - x_min) / (x_max - x_min)) * self.screen_width
        y_screen = self.screen_height - ((y_world - y_min) / (y_max - y_min)) * self.screen_height
        return x_screen, y_screen

    def generate_damped_sine(self, x_min=0.0, x_max=10.0, num_points=500, alpha=0.5, omega=2.0 * np.pi):
        """
        Gera a função de onda amortecida: f(x) = exp(-alpha * x) * sin(omega * x)
        """
        x = np.linspace(x_min, x_max, num_points)
        y = np.exp(-alpha * x) * np.sin(omega * x)
        return x, y

    def generate_lissajous(self, a=3, b=4, delta=np.pi/2, num_points=1000):
        """
        Gera curvas paramétricas de Lissajous: x(t) = sin(a*t + delta), y(t) = sin(b*t)
        """
        t = np.linspace(0, 2 * np.pi, num_points)
        x = np.sin(a * t + delta)
        y = np.sin(b * t)
        return x, y

    def plot_function(self, x, y, title="MBPLOT - Visualização de Função"):
        """
        Plota o gráfico com estilo retrô similar ao ambiente gráfico DOS.
        """
        x_min, x_max = np.min(x), np.max(x)
        y_min, y_max = np.min(y), np.max(y)

        # Mapeamento para resolução de tela simulada
        x_pixel, y_pixel = self.world_to_screen(x, y, x_min, x_max, y_min, y_max)

        plt.figure(figsize=(9, 6), facecolor='black')
        ax = plt.axes()
        ax.set_facecolor('black')

        # Desenhar linha estilo monitor VGA clássico (Verde / Ciano)
        plt.plot(x_pixel, y_pixel, color='#00FF66', linewidth=1.5, label='Sinal Processado')

        plt.title(title, color='white', fontsize=12, fontweight='bold')
        plt.xlabel("Pixel X (Viewport)", color='white')
        plt.ylabel("Pixel Y (Viewport Invertido)", color='white')
        plt.tick_params(colors='white')
        plt.grid(True, color='#333333', linestyle='--')
        plt.xlim(0, self.screen_width)
        plt.ylim(self.screen_height, 0) # Invertido igual coordenada de tela
        plt.legend(facecolor='black', edgecolor='white', labelcolor='white')
        
        plt.tight_layout()
        plt.show()

if __name__ == "__main__":
    simulator = MBPlotSimulator(screen_width=640, screen_height=480)

    # 1. Plotar Onda Senoidal Amortecida
    x_func, y_func = simulator.generate_damped_sine(x_min=0, x_max=5, num_points=400, alpha=0.6, omega=4.0*np.pi)
    simulator.plot_function(x_func, y_func, title="MBPLOT Simulação: Onda Amortecida f(x) = e^(-a*x) * sin(w*x)")

    # 2. Plotar Figura de Lissajous
    x_liss, y_liss = simulator.generate_lissajous(a=5, b=6, delta=np.pi/4)
    simulator.plot_function(x_liss, y_liss, title="MBPLOT Simulação: Curva Paramétrica de Lissajous")