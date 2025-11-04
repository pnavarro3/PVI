#include "Vrekrer_scpi_parser.h"
SCPI_Parser InstVirtPA;

//Serial
String entradaSerial = "";
bool entradaCompleta = false;

//Parte bascula
#include "HX711.h"
const int DOUT = A1;
const int CLK = A0;
HX711 balanza;

//Parte bombas
//Para Vaciar
int ENA1 = 10;
int IN1 = 9;
int IN2 = 8;

//Para llenar
int ENA2 = 5;
int IN3 = 7;
int IN4 = 6;

//Control

int margen = 10;
int peso;
int valor;
bool flag = false;


void setup() {
  //Parte bascula
  Serial.begin(9600);

  balanza.begin(DOUT, CLK);

  balanza.set_scale(738);  //La escala por defecto es 1
  balanza.tare(20);        //El peso actual es considerado Tara.
  

  InstVirtPA.SetCommandTreeBase(F("STATus:OPERation"));
  InstVirtPA.RegisterCommand(F(":VACiar"), &vaciar);
  InstVirtPA.RegisterCommand(F(":LLEnar"), &llenar);
  InstVirtPA.RegisterCommand(F(":PARar"), &parar);
  InstVirtPA.RegisterCommand(F(":CONsigna#"), &consigna);
  InstVirtPA.RegisterCommand(F(":TARCAL"), &tarar);
  InstVirtPA.SetCommandTreeBase(F("STATus"));
  InstVirtPA.RegisterCommand(F(":VOLumen?"), &medir);
  InstVirtPA.SetCommandTreeBase(F("SYSTem"));
  InstVirtPA.RegisterCommand(F(":VERSion?"), &identificar);


  //Parte bomba
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

    if (flag) {
      if (peso > valor + margen) {
        analogWrite(ENA1, 255);
        analogWrite(ENA2, 0);
      } 
        else if (peso < valor - margen) {
        analogWrite(ENA2, 255);
        analogWrite(ENA1, 0);
      } 
        else {
        analogWrite(ENA1, 0);
        analogWrite(ENA2, 0);
      }
    peso = balanza.get_units(10);
  }
}

void identificar(SCPI_C commands, SCPI_P parameters, Stream& interface) {
  flag = false;
  interface.println("Arduino 2.3.6 Instrumento virtual V3 PA");
}

void llenar(SCPI_C commands, SCPI_P parameters, Stream& interface) {
  flag = false;
  analogWrite(ENA2, 255);
  analogWrite(ENA1, 0);
  interface.println("Llenando");
}
void vaciar(SCPI_C commands, SCPI_P parameters, Stream& interface) {
  flag = false;
  analogWrite(ENA1, 255);
  analogWrite(ENA2, 0);
  interface.println("Vaciando");
}
void parar(SCPI_C commands, SCPI_P parameters, Stream& interface) {
  flag = false;
  analogWrite(ENA1, 0);
  analogWrite(ENA2, 0);
  interface.println("Parar");
}
void tarar(SCPI_C commands, SCPI_P parameters, Stream& interface) {
  flag = false;
  analogWrite(ENA1, 0);
  analogWrite(ENA2, 0);
  balanza.set_scale(738);
  balanza.tare(20);
  interface.println("Calibrado");
}
void medir(SCPI_C commands, SCPI_P parameters, Stream& interface) {
  peso = balanza.get_units(10);
  interface.println(peso);
}
void consigna(SCPI_C commands, SCPI_P parameters, Stream& interface) {
  if (parameters.Size() > 0) {  
    valor = atoi(parameters[0]);
    flag = true;
  }  
}

