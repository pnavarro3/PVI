#include "Vrekrer_scpi_parser.h"
SCPI_Parser InstVirtPA;

#include "HX711.h"
const int DOUT = A1;
const int CLK = A0;
HX711 balanza;

int ENA1 = 10;
int IN1 = 9;
int IN2 = 8;
int ENA2 = 5;
int IN3 = 7;
int IN4 = 6;

int margen = 10;
int peso;
int pesomedir;
int valor;
bool flag = false;
int num_ciclos = 0;
int ciclos_completados = 0;
bool en_ciclo = false;
bool llenando = true;
unsigned long ultimo_muestreo = 0;
const unsigned long intervalo_muestreo = 1000; // 1 segundo

void setup() {
  Serial.begin(9600);
  balanza.begin(DOUT, CLK);
  balanza.set_scale(738);
  balanza.tare(20);

  InstVirtPA.SetCommandTreeBase(F("STATus:OPERation"));
  InstVirtPA.RegisterCommand(F(":LLENar"), &llenar);
  InstVirtPA.RegisterCommand(F(":VACiar"), &vaciar);
  InstVirtPA.RegisterCommand(F(":PARar"), &parar);
  InstVirtPA.RegisterCommand(F(":CONsigna#"), &consigna);
  InstVirtPA.RegisterCommand(F(":TARCAL"), &tarar);
  InstVirtPA.RegisterCommand(F(":CIClos#"), &ciclos);
  InstVirtPA.SetCommandTreeBase(F("ESTAdo"));
  InstVirtPA.RegisterCommand(F(":MEDicion?"), &medir);
  InstVirtPA.RegisterCommand(F(":ENCiclo?"), &en_ciclo_query);
  InstVirtPA.SetCommandTreeBase(F("SYSTem"));
  InstVirtPA.RegisterCommand(F(":VERSion?"), &identificar);

  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(ENA1, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  pinMode(ENA2, OUTPUT);

  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
}

void loop() {
  InstVirtPA.ProcessInput(Serial, "\n");
  control_volumen();
  control_ciclos();
}

void control_volumen() {
  if (flag && !en_ciclo) {
    peso = balanza.get_units(10);
    if (peso > valor + margen) {
      analogWrite(ENA1, 255);
      analogWrite(ENA2, 0);
    } else if (peso < valor - margen) {
      analogWrite(ENA2, 255);
      analogWrite(ENA1, 0);
    } else {
      analogWrite(ENA1, 0);
      analogWrite(ENA2, 0);
    }
  }
}

void control_ciclos() {
  if (en_ciclo) {
    unsigned long tiempo_actual = millis();
    
    // Solo medir cada 200ms para no bloquear el serial
    if (tiempo_actual - ultimo_muestreo >= 200) {
      ultimo_muestreo = tiempo_actual;
      peso = balanza.get_units(10);
      
      if (llenando) {
        // Llenar hasta alcanzar 600 + margen
        if (peso < 600 + margen) {
          analogWrite(ENA2, 255);
          analogWrite(ENA1, 0);
        } else {
          // Alcanzado el objetivo, parar y cambiar a vaciado
          analogWrite(ENA1, 0);
          analogWrite(ENA2, 0);
          llenando = false;
        }
      } else {
        // Vaciar hasta alcanzar 0 - margen
        if (peso > 0 - margen) {
          analogWrite(ENA1, 255);
          analogWrite(ENA2, 0);
        } else {
          // Alcanzado el objetivo, parar y completar ciclo
          analogWrite(ENA1, 0);
          analogWrite(ENA2, 0);
          ciclos_completados++;
          
          if (ciclos_completados < num_ciclos) {
            llenando = true;
          } else {
            en_ciclo = false;
          }
        }
      }
    }
  }
}

void identificar(SCPI_C commands, SCPI_P parameters, Stream& interface) {
  en_ciclo = false;
  flag = false;
  interface.println("Arduino 2.3.6 Instrumento virtual V3 PA");
}

void llenar(SCPI_C commands, SCPI_P parameters, Stream& interface) {
  en_ciclo = false;
  flag = false;
  analogWrite(ENA2, 255);
  analogWrite(ENA1, 0);
  interface.println("ACK");
}

void vaciar(SCPI_C commands, SCPI_P parameters, Stream& interface) {
  en_ciclo = false;
  flag = false;
  analogWrite(ENA1, 255);
  analogWrite(ENA2, 0);
  interface.println("ACK");
}

void parar(SCPI_C commands, SCPI_P parameters, Stream& interface) {
  en_ciclo = false;
  flag = false;
  analogWrite(ENA1, 0);
  analogWrite(ENA2, 0);
  interface.println("ACK");
}

void tarar(SCPI_C commands, SCPI_P parameters, Stream& interface) {
  en_ciclo = false;
  flag = false;
  analogWrite(ENA1, 0);
  analogWrite(ENA2, 0);
  balanza.set_scale(738);
  balanza.tare(20);
  interface.println("ACK");
}

void medir(SCPI_C commands, SCPI_P parameters, Stream& interface) {
  peso = balanza.get_units(10);
  interface.println(peso);
}

void consigna(SCPI_C commands, SCPI_P parameters, Stream& interface) {
  if (parameters.Size() > 0) {
    valor = atoi(parameters[0]);
    flag = true;
    interface.println("ACK");
  } else {
    interface.println("ERR");
  }
}

void ciclos(SCPI_C commands, SCPI_P parameters, Stream& interface) {
  if (parameters.Size() > 0) {
    num_ciclos = atoi(parameters[0]);
    ciclos_completados = 0;
    en_ciclo = true;
    llenando = true;
    flag = false;
    ultimo_muestreo = millis();
    interface.println("ACK");
  } else {
    interface.println("ERR");
  }
}

void en_ciclo_query(SCPI_C commands, SCPI_P parameters, Stream& interface) {
  if (en_ciclo) {
    interface.println("1");
  } else {
    interface.println("0");
  }
}
