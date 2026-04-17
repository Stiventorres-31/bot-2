import datetime
import requests
import telebot
import time
import os
import os

# --- CONFIGURACIÓN PRINCIPAL ---
TOKEN = "8622823730:AAF7ZLp6u9BZv2H-RUDbmMdpqTxMLK5TOL8"
CHAT_ID = "-1003550654404"
URL_API = "https://aviator-round-production.up.railway.app/api/aviator/rounds/1?limit=10"

# --- PARÁMETROS DE ESTRATEGIA ---
BANKROLL = 1000000
STAKE_1 = 0.01   # 1% de la banca
STAKE_2 = 0.027  # 2.7% de la banca (Gale)
TARGET_MULTIPLIER = 2.00

# --- GESTIÓN DE RIESGO ---
STOP_LOSS_TOTAL = 0.20  # Pausa larga si se pierde el 20%
PAUSE_TIME_LOSS = 300   # 5 minutos de pausa si se pierde un Gale
COOLDOWN_ROUNDS = 4    # Mínimo de rondas entre entradas (frecuencia simple)

class AviatorInfinityBot:
    def __init__(self):
        self.bot = telebot.TeleBot(token=TOKEN, parse_mode='MARKDOWN')
        self.balance = BANKROLL
        self.profit = 0
        self.history_signals = []
        
        # Estados de la operación
        self.entrada_en_curso = False
        self.gale_pendiente = False
        self.pause_until = None
        self.last_id_procesado = None # Para evitar mensajes dobles
        self.trades_history = []     # Historial ["win", "loss"]
        self.round_count = 0        # Contador de rondas procesadas
        self.last_trade_round = 0   # Ronda de la última entrada

    def enviar_telegram(self, texto):
        try:
            self.bot.send_message(chat_id=CHAT_ID, text=texto)
        except Exception as e:
            print(f"❌ Error enviando a Telegram: {e}")

    # --- MENSAJES ---
    def msg_entrada(self):
        msg = "🚀 *ENTRADA DETECTADA*\n\n"
        msg += f"🎯 Punto de Retiro: *{TARGET_MULTIPLIER:.2f}x*\n"
        msg += f"💰 Inversión sugerida: *{STAKE_1*100:.1f}%*\n\n"
        msg += "⚠️ *Ejecutar en la siguiente ronda*"
        self.enviar_telegram(msg)

    def msg_gale(self):
        msg = "⚠️ *MARTINGALA 1*\n\n"
        msg += "El avión se fue antes. Entramos de nuevo.\n"
        msg += f"💰 Inversión: *{STAKE_2*100:.1f}%*\n"
        msg += f"🎯 Retiro: *{TARGET_MULTIPLIER:.2f}x*"
        self.enviar_telegram(msg)

    def msg_win(self, valor):
        msg = f"✅ *¡WIN {valor:.2f}x!*\n"
        msg += "Estrategia aplicada con éxito."
        self.enviar_telegram(msg)

    def msg_loss(self, valor):
        msg = f"❌ *CICLO CERRADO {valor:.2f}x*\n"
        msg += "Gale fallido. Pausamos 5 min para analizar."
        self.enviar_telegram(msg)

    def msg_resumen(self):
        if not self.history_signals: return
        msg = "📊 *RESUMEN DE OPERACIONES*\n\n"
        for s in self.history_signals:
            icon = "✅" if s['status'] == 'win' else "❌"
            msg += f"{icon} Multiplicador: {s['res']:.2f}x (G{s['gale']})\n"
        
        self.enviar_telegram(msg)
        self.history_signals = []

    # --- LÓGICA DE FILTRADO ---
    # --- LÓGICA DE FILTRADO ---
    def filtro_cuota_2(self, results):
        """
        Filtro optimizado para buscar cuotas >= 2.0
        """
        current_index = self.round_count
        last_trade_index = self.last_trade_round
        trades = self.trades_history

        if len(results) < 5:
            return False

        last5 = results[-5:]
        last4 = results[-4:]
        last3 = results[-3:]

        # ==============================
        # COOLDOWN
        # ==============================
        if current_index - last_trade_index < COOLDOWN_ROUNDS:
            return False

        # ==============================
        # ❌ BLOQUEOS
        # ==============================

        # Crash reciente o secuencia de crashes
        if any(r < 1.30 for r in last3) or last3[-1] < 1.40:
            return False

        # Mercado débil (zona débil fuerte last3)
        if sum(1 for r in last3 if r < 1.50) >= 2:
            return False

        # Bloquear zona débil fuerte (last4)
        if sum(1 for r in last4 if r < 1.50) >= 2:
            return False

        # El bloqueo por pérdida se maneja con la pausa global en ejecutar_ciclo

        # ==============================
        # ✅ CONDICIONES PRINCIPALES
        # ==============================

        # Continuidad fuerte
        if sum(1 for r in last3 if r >= 1.70) < 2:
            return False

        # Evitar rachas continuas (no entrar si las últimas 3 fueron >= 1.70)
        if all(r >= 1.70 for r in last3):
            return False

        # Confirmación media-alta
        if sum(1 for r in last5 if r >= 1.80) < 2:
            return False

        # ==============================
        # 🧠 SCORE DE CALIDAD
        # ==============================

        score = 0

        for r in last5:
            if r >= 2.0:
                score += 2
            elif r >= 1.7:
                score += 1
            elif r < 1.5:
                score -= 2

        if score < 3:
            return False

        return True

    def obtener_api(self):
        try:
            response = requests.get(URL_API, timeout=10)
            return response.json()
        except Exception as e:
            print(f"⚠️ Error de conexión API: {e}")
            return None

    def ejecutar_ciclo(self):
        print("🚀 Bot Aviator Infinity 24/7 iniciado...")
        
        while True:
            try:
                # 1. Control de Pausa
                if self.pause_until:
                    if datetime.datetime.now() < self.pause_until:
                        time.sleep(30)
                        continue
                    else:
                        print("⏳ Pausa terminada. Retomando búsqueda...")
                        self.pause_until = None

                # 2. Obtener datos
                data = self.obtener_api()
                if not data or not isinstance(data, list):
                    time.sleep(2)
                    continue

                ronda_actual = data[0]
                ronda_id = ronda_actual['id'] # El ID de tu API (ej: 31359)
                ronda_val = float(ronda_actual['max_multiplier'])
                historial_completo = [float(x['max_multiplier']) for x in data]

                # 3. FILTRO ANTI-DUPLICADOS (Crucial para no enviar mensajes dobles)
                if ronda_id == self.last_id_procesado:
                    time.sleep(1) # Esperar que la API actualice la siguiente ronda
                    continue
                
                # Si llegamos aquí, es una ronda nueva
                self.last_id_procesado = ronda_id
                self.round_count += 1
                print(f"📈 Nueva Ronda detectada: {ronda_id} -> {ronda_val}x (Total: {self.round_count})")

                # 4. PROCESAR SI HAY UNA APUESTA ACTIVA
                if self.entrada_en_curso and not self.gale_pendiente:
                    if ronda_val >= TARGET_MULTIPLIER:
                        ganancia = (BANKROLL * STAKE_1) * (TARGET_MULTIPLIER - 1)
                        self.profit += ganancia
                        self.history_signals.append({'status': 'win', 'gale': 0, 'res': ronda_val})
                        self.trades_history.append("win")
                        self.msg_win(ronda_val)
                        self.entrada_en_curso = False
                    else:
                        # Falló la primera, activar Gale
                        self.gale_pendiente = True
                        self.msg_gale()
                    continue

                elif self.gale_pendiente:
                    if ronda_val >= TARGET_MULTIPLIER:
                        ganancia_neta = ((BANKROLL * STAKE_2) * (TARGET_MULTIPLIER - 1)) - (BANKROLL * STAKE_1)
                        self.profit += ganancia_neta
                        self.history_signals.append({'status': 'win', 'gale': 1, 'res': ronda_val})
                        self.trades_history.append("win")
                        self.msg_win(ronda_val)
                    else:
                        perdida_total = (BANKROLL * STAKE_1) + (BANKROLL * STAKE_2)
                        self.profit -= perdida_total
                        self.history_signals.append({'status': 'loss', 'gale': 1, 'res': ronda_val})
                        self.trades_history.append("loss")
                        self.msg_loss(ronda_val)
                        # Pausar tras pérdida de ciclo
                        self.pause_until = datetime.datetime.now() + datetime.timedelta(seconds=PAUSE_TIME_LOSS)
                    
                    self.entrada_en_curso = False
                    self.gale_pendiente = False
                    continue

                # 5. BUSCAR NUEVA SEÑAL (Si no hay nada en curso)
                # historial_completo viene [reciente0, reciente1, ..., antiguo9]
                # lo invertimos para que sea cronológico [antiguo, ..., reciente] como pide el filtro
                historial_cronologico = historial_completo[::-1]
                if self.filtro_cuota_2(historial_cronologico):
                    self.msg_entrada()
                    self.entrada_en_curso = True
                    self.last_trade_round = self.round_count

                # 6. ENVIAR RESUMEN CADA 10 SEÑALES
                if len(self.history_signals) >= 10:
                    self.msg_resumen()

            except Exception as e:
                print(f"💥 Error en el bucle: {e}")
                time.sleep(5)

if __name__ == "__main__":
    # Iniciar Bot
    aviator_bot = AviatorInfinityBot()
    aviator_bot.ejecutar_ciclo()