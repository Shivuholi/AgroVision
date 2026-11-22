import time
import json
import os
import sys
from datetime import datetime
import paho.mqtt.client as mqtt

MQTT_BROKER = os.getenv("MQTT_BROKER", "broker.emqx.io")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))

# Color formatting for terminal
CYAN    = "\033[96m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
MAGENTA = "\033[95m"
BOLD    = "\033[1m"
RESET   = "\033[0m"

last_telemetry_time = 0

def format_hex(data: bytes) -> str:
    """Format raw bytes as a formatted hex dump."""
    hex_str = " ".join(f"{b:02X}" for b in data[:32])
    if len(data) > 32:
        hex_str += f" ... (+{len(data)-32} more bytes)"
    return hex_str

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"{GREEN}[CONNECTED]{RESET} Attached to Broker {CYAN}{MQTT_BROKER}:{MQTT_PORT}{RESET}")
        client.subscribe("agrovision/#", qos=1)
        print(f"{GREEN}[SNIFFER ACTIVE]{RESET} Listening on topic pattern: {YELLOW}agrovision/#{RESET}\n")
        print(f"{'TIMESTAMP':<12} | {'TYPE':<10} | {'TOPIC':<32} | {'BYTES':<8} | {'EFFICIENCY':<10} | {'LATENCY'}")
        print("-" * 95)
    else:
        print(f"{RED}[ERROR]{RESET} Connection failed with code {rc}")

def on_message(client, userdata, msg):
    global last_telemetry_time
    now = time.time()
    time_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]

    raw_payload = msg.payload
    payload_len = len(raw_payload)
    topic_len = len(msg.topic)
    
    # MQTT Fixed Header (2 bytes) + Variable Header / Topic (topic_len + 2 bytes)
    mqtt_frame_est = 2 + (topic_len + 2) + payload_len
    efficiency = (payload_len / mqtt_frame_est) * 100

    topic = msg.topic
    msg_type = "DATA"
    color = CYAN
    latency_str = "-"

    if "telemetry" in topic:
        msg_type = "TELEMETRY"
        color = GREEN
        last_telemetry_time = now
    elif "cmd" in topic:
        msg_type = "COMMAND"
        color = MAGENTA
        if last_telemetry_time > 0:
            latency_ms = (now - last_telemetry_time) * 1000
            latency_str = f"{latency_ms:.1f} ms"
    elif "status" in topic:
        msg_type = "LWT/STATUS"
        color = RED if b"offline" in raw_payload else YELLOW

    print(f"{time_str:<12} | {color}{msg_type:<10}{RESET} | {topic:<32} | {mqtt_frame_est:<8}B | {efficiency:>5.1f}%     | {color}{latency_str}{RESET}")
    print(f"  {BOLD}Hex Dump:{RESET}  {format_hex(raw_payload)}")
    
    try:
        parsed = json.loads(raw_payload.decode("utf-8"))
        summary = ", ".join(f"{k}={v}" for k, v in parsed.items())
        print(f"  {BOLD}Decoded:{RESET}   {{{summary}}}")
        if "lux" in parsed:
            lux_val = float(parsed["lux"])
            ppfd_val = lux_val * 0.0185
            print(f"  {BOLD}Biological:{RESET} Lux={lux_val:.1f} lx -> PPFD={ppfd_val:.1f} \u03bcmol/m\u00b2/s (Usable Plant Light)")
    except Exception:
        print(f"  {BOLD}Raw Text:{RESET}  {raw_payload.decode('utf-8', errors='replace')}")

    # Comparison Callout with HTTP
    http_equivalent_est = mqtt_frame_est + 850 # ~850 bytes typical HTTP headers
    saved_bytes = http_equivalent_est - mqtt_frame_est
    print(f"  {BOLD}Comparison:{RESET} MQTT frame: {BOLD}{mqtt_frame_est} B{RESET} vs HTTP equivalent: {BOLD}{http_equivalent_est} B{RESET} ({GREEN}{saved_bytes} B saved{RESET})\n")

def main():
    print(f"{BOLD}================================================================={RESET}")
    print(f"{CYAN}       AgroVision Real-Time Network Layer Protocol Inspector      {RESET}")
    print(f"{BOLD}================================================================={RESET}")
    print(f"Target: Monitoring all raw packets on {MQTT_BROKER}...\n")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="agrovision_packet_inspector")
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_forever()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Inspector stopped by user.{RESET}")
        client.disconnect()

if __name__ == "__main__":
    main()
