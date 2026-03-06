#include "gpio_config.h"
#include "pit_config.h"
#include "uart_config.h"
#include "MultiturnOpticalEncoder.h"
#include "Function.h"
#include "SensAREncoder.h"
#include "ModBus.h"

//==============================================================================
// DEFINES
//==============================================================================


//#define POWERON_STANDBY_TIME 					1800                                      //1.8s

//==============================================================================
// DATA
//==============================================================================

void MNS_SinCos_MaxMin(void);
void MultiturnOpticalEncoderLedDac(void);
void MultiturnOpticalEncoderSectorCollect(void);
void MultiturnOpticalEncoderMTABContinuousCheck(void);
void MultiturnOpticalEncoderHallContinuousCheck(void);

strMulOptEnc   MultiturnOpticalEncoder = {0};
strICPNH2612  PNH2612 = {0}; 


//volatile uint8_t   EncoderEepromData[2][128] = {0};

volatile uint8_t   Cnt_0x85 = 0;
volatile uint8_t   Cnt_MSinDataMax = 0;
volatile uint8_t   Cnt_MSinDataMin = 0;
volatile uint8_t   Cnt_NSinDataMax = 0;
volatile uint8_t   Cnt_NSinDataMin = 0;
volatile uint8_t   Cnt_SSinDataMax = 0;
volatile uint8_t   Cnt_SSinDataMin = 0;

volatile uint8_t   Cnt_MCosDataMax = 0;
volatile uint8_t   Cnt_MCosDataMin = 0;
volatile uint8_t   Cnt_NCosDataMax = 0;
volatile uint8_t   Cnt_NCosDataMin = 0;
volatile uint8_t   Cnt_SCosDataMax = 0;
volatile uint8_t   Cnt_SCosDataMin = 0;

extern volatile uint8_t  Calibration_Mode;

extern volatile uint8_t  Work_Alarm;
extern volatile uint32_t PITCnt;
extern volatile uint8_t  PCBAFctResult;
extern uart_transfer_t uart0_transfer;


// 状态码定义 (用于 .Check)
#define ENC_STATUS_TESTING      0
#define ENC_STATUS_PASS         1
#define ENC_STATUS_ERR_GLITCH   2
#define ENC_STATUS_ERR_JITTER   3
#define ENC_STATUS_ERR_COUNT    4

// 物理->逻辑 映射表 (0->1->2->3)
static const uint8_t MTAB_Map[4] = {3, 0, 2, 1}; // 物理 1,3,2,0 -> 逻辑 0,1,2,3
static const uint8_t HALL_Map[4] = {0, 3, 2, 1}; // 物理 0,3,2,1 -> 逻辑 0,1,2,3

//==============================================================================
// MultiturnOpticalEncoderTXOneByte
//==============================================================================
void MultiturnOpticalEncoderTXOneByte(volatile uint8_t Idle)
{
  MultiturnOpticalEncoder.TimeoutCnt ++;
  MultiturnOpticalEncoder.TxData[0] = Idle;                                         
  uart0_transfer.data = (uint8_t *)&MultiturnOpticalEncoder.TxData[0];
  uart0_transfer.dataSize = 1;           
  Encoder485DE();                                                         
  for (volatile uint8_t i=0; i<5; i++);
  UART_SendDMA0(&uart0_transfer);   
}
void MultiturnOpticalEncoderMNSAnalogMaxSampling(void)
{
  if(MultiturnOpticalEncoder.Flag.bit.AMD == 1){
    MNS_SinCos_MaxMin();
  }else if(MultiturnOpticalEncoder.Flag.bit.AMD == 2){            
      if(MultiturnOpticalEncoder.Flag.bit.MNSAMDOneLapCheck == 1){
        if(PNH2612.MNSAnalogChekcCnt < 10000){//60rpm,8k频率，采样9k点，从第1000开始
          PNH2612.MNSAnalogChekcCnt ++;
          if(PNH2612.MNSAnalogChekcCnt > 1000){
            MNS_SinCos_MaxMin();
          }
        }else{
          PNH2612.MNSAnalogChekcCnt = 0;
          MultiturnOpticalEncoder.Flag.bit.MNSAMDOneLapCheck = 2;
          MotorEncoder.TestItem = MultiturnOpticalEncoderMNSAnalogMaxCheckTest;
        }                
      }else{
        MNS_SinCos_MaxMin();
        if(PNH2612.MNSAnalogChekcCnt < 2000){//60rpm,8k频率，四分之一圈就是2k
          PNH2612.MNSAnalogChekcCnt ++;
        }else{
          PNH2612.MNSAnalogChekcCnt = 0;
          MotorEncoder.TestItem = MultiturnOpticalEncoderMNSAnalogMaxCheckTest;
        }              
      }
    }  
}
//==============================================================================
// Encoder_RX
//==============================================================================
__ramfunc void MultiturnOpticalEncoderRX(void)
{
    //static uint8_t   i = 0;
    MultiturnOpticalEncoder.RxData[MultiturnOpticalEncoder.RxDataCnt++] = UART0->D;                                                  //Recieve request to auto clear flag     
    
    if(MultiturnOpticalEncoder.RxDataCnt >= 1){
      switch(MultiturnOpticalEncoder.RxData[0]){
      case 0x1A:
        if(MultiturnOpticalEncoder.RxDataCnt == 11){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          MultiturnOpticalEncoder.Status.all = MultiturnOpticalEncoder.RxData[1];
          MultiturnOpticalEncoder.SingleTurnPosition = ((MultiturnOpticalEncoder.RxData[4] << 16) | (MultiturnOpticalEncoder.RxData[3] << 8) | MultiturnOpticalEncoder.RxData[2]) & 0xFFFFFFFF;
          MotorEncoder.SingleTurnPosition = MultiturnOpticalEncoder.SingleTurnPosition;
          MultiturnOpticalEncoder.ResolutionID = MultiturnOpticalEncoder.RxData[5];
          MotorEncoder.ResolutionID = MultiturnOpticalEncoder.ResolutionID;
          MultiturnOpticalEncoder.MultiTurnPosition = ((MultiturnOpticalEncoder.RxData[7] << 8) | MultiturnOpticalEncoder.RxData[6]) & 0xFFFF;
          MotorEncoder.MultiTurnPosition = MultiturnOpticalEncoder.MultiTurnPosition;
          MultiturnOpticalEncoder.Error.all = MultiturnOpticalEncoder.RxData[9];
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, 10); 
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[10]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            Work_Alarm = 0x02;
          }
        }
        break;      
      case 0x02:
        if(MultiturnOpticalEncoder.RxDataCnt == 6){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;   
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          MultiturnOpticalEncoder.Status.all = MultiturnOpticalEncoder.RxData[1];
          MultiturnOpticalEncoder.SingleTurnPosition = ((MultiturnOpticalEncoder.RxData[4] << 16) | (MultiturnOpticalEncoder.RxData[3] << 8) | MultiturnOpticalEncoder.RxData[2]) & 0xFFFFFFFF;
          MotorEncoder.SingleTurnPosition = MultiturnOpticalEncoder.SingleTurnPosition;
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, 5);
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[5]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            Work_Alarm = 0x02;
          }
        }
        break;
      case 0x62:
        if(MultiturnOpticalEncoder.RxDataCnt == 6){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;   
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          MultiturnOpticalEncoder.Status.all = MultiturnOpticalEncoder.RxData[1];
          MultiturnOpticalEncoder.SingleTurnPosition = ((MultiturnOpticalEncoder.RxData[4] << 16) | (MultiturnOpticalEncoder.RxData[3] << 8) | MultiturnOpticalEncoder.RxData[2]) & 0xFFFFFFFF;
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, 5);
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[5]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            Work_Alarm = 0x02;
          }
        }
        break;        
      case 0xEA:
        if(MultiturnOpticalEncoder.RxDataCnt==4){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          MultiturnOpticalEncoder.Eeprom.ReturnAddress = MultiturnOpticalEncoder.RxData[1] & 0x7F;
          if(MultiturnOpticalEncoder.Eeprom.ReturnAddress == MultiturnOpticalEncoderPNSAddress){
            MultiturnOpticalEncoder.Eeprom.ReturnPage = MultiturnOpticalEncoder.RxData[2];
            MultiturnOpticalEncoder.Eeprom.Status.bit.Busy = (MultiturnOpticalEncoder.RxData[1] >> 7) & 0xFF;
            MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.ReturnPage][MultiturnOpticalEncoder.Eeprom.ReturnAddress] = MultiturnOpticalEncoder.RxData[2];   
          }else if(MultiturnOpticalEncoder.Eeprom.ReturnAddress < MultiturnOpticalEncoderPNSAddress){
            MultiturnOpticalEncoder.Eeprom.Status.bit.Busy = (MultiturnOpticalEncoder.RxData[1] >> 7) & 0xFF;
            MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.ReturnPage][MultiturnOpticalEncoder.Eeprom.ReturnAddress] = MultiturnOpticalEncoder.RxData[2];            
          }   
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, 3);
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[3]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnOpticalEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }
        }   
        break;
      case 0x32:
        if(MultiturnOpticalEncoder.RxDataCnt==4){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          MultiturnOpticalEncoder.Eeprom.Address = MultiturnOpticalEncoder.RxData[1];
          MultiturnOpticalEncoder.Eeprom.Data = MultiturnOpticalEncoder.RxData[2];
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, 3);
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[3]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            Work_Alarm = 0x02;
          }
          MultiturnOpticalEncoder.Flag.bit.CF32 = 0x00;
        }          
        break;
      case 0x85://读取3码道6个ADC,MTAB HALL
        if(MultiturnOpticalEncoder.RxDataCnt == 12){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;  
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          PNH2612.M.SinData = MultiturnOpticalEncoder.RxData[1] | ((MultiturnOpticalEncoder.RxData[7] >> 4) << 8);
          PNH2612.M.CosData = MultiturnOpticalEncoder.RxData[2] | ((MultiturnOpticalEncoder.RxData[7] & 0x0F) << 8);          
          PNH2612.N.SinData = MultiturnOpticalEncoder.RxData[3] | ((MultiturnOpticalEncoder.RxData[8] >> 4) << 8);
          PNH2612.N.CosData = MultiturnOpticalEncoder.RxData[4] | ((MultiturnOpticalEncoder.RxData[8] & 0x0F) << 8);
          PNH2612.S.SinData = MultiturnOpticalEncoder.RxData[5] | ((MultiturnOpticalEncoder.RxData[9] >> 4) << 8);
          PNH2612.S.CosData = MultiturnOpticalEncoder.RxData[6] | ((MultiturnOpticalEncoder.RxData[9] & 0x0F) << 8);            
          PNH2612.HallSector = (MultiturnOpticalEncoder.RxData[10] & 0x30) >> 4;
          PNH2612.MTABSector = (MultiturnOpticalEncoder.RxData[10] & 0x03);  
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, 11);
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[11]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnOpticalEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }
          MultiturnOpticalEncoderMNSAnalogMaxSampling();
          MultiturnOpticalEncoderSectorCollect();
          MultiturnOpticalEncoderLedDac();
          MultiturnOpticalEncoderMTABContinuousCheck();
          MultiturnOpticalEncoderHallContinuousCheck();
        }
        break;      
      case 0x0D://读取3码道位置值 注1：ADC当前采样后，发送
        if(MultiturnOpticalEncoder.RxDataCnt == 8){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0; 
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          PNH2612.M.Absolute = MultiturnOpticalEncoder.RxData[1] | (MultiturnOpticalEncoder.RxData[2] << 8);
          PNH2612.N.Absolute = MultiturnOpticalEncoder.RxData[3] | (MultiturnOpticalEncoder.RxData[4] << 8);
          PNH2612.S.Absolute = MultiturnOpticalEncoder.RxData[5] | (MultiturnOpticalEncoder.RxData[6] << 8);
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, 7);
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[7]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnOpticalEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }
        }
        break;      
      case 0x15://读取MNdelta值及MTsector
        if(MultiturnOpticalEncoder.RxDataCnt == 8){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;   
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          PNH2612.MNdelta = MultiturnOpticalEncoder.RxData[1] | (MultiturnOpticalEncoder.RxData[2] << 8);
          PNH2612.MTABSector = MultiturnOpticalEncoder.RxData[3];
          PNH2612.Q4D = MultiturnOpticalEncoder.RxData[4];
          PNH2612.Q14D = MultiturnOpticalEncoder.RxData[5] | (MultiturnOpticalEncoder.RxData[6] << 8);
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, 7);
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[7]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnOpticalEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }          
        }
        break;        
      case 0x9D://读取当前位置值 注1：ADC当前采样后，发送 注2:绝对位置为23bit时，ABS3全为0，ABS2的最高位为0；
        if(MultiturnOpticalEncoder.RxDataCnt==6){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;  
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          PNH2612.AbsolutePosition = MultiturnOpticalEncoder.RxData[1] | (MultiturnOpticalEncoder.RxData[2] << 8) | (MultiturnOpticalEncoder.RxData[3] << 16) | (MultiturnOpticalEncoder.RxData[4] << 24);
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, 5);
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[5]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnOpticalEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }          
        }  
        break;
      case 0x25://读取当前位置值及Hall逻辑电平值、MTAB逻辑电平
        if(MultiturnOpticalEncoder.RxDataCnt==10){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;  
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          PNH2612.AbsolutePosition = MultiturnOpticalEncoder.RxData[1] | (MultiturnOpticalEncoder.RxData[2] << 8) | (MultiturnOpticalEncoder.RxData[3] << 16) | (MultiturnOpticalEncoder.RxData[4] << 24);
          PNH2612.HallSector = (MultiturnOpticalEncoder.RxData[5] & 0x30) >> 4;
          PNH2612.MTABSector = (MultiturnOpticalEncoder.RxData[5] & 0x03);
          PNH2612.MTABSectorraw = (MultiturnOpticalEncoder.RxData[5] & 0x0C) >> 2;
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, 9);
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[9]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnOpticalEncoder.XorCrcError;
            Work_Alarm = 0x02;
          } 
        }          
        break;
      case 0xAD://读eeprom/flash功能 0xAD  | PAGE | ADF1 | DNUM | CRC
        if(MultiturnOpticalEncoder.RxDataCnt==(MultiturnOpticalEncoder.Eeprom.SetDNum + 5)){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          MultiturnOpticalEncoder.Eeprom.ReturnPage = MultiturnOpticalEncoder.RxData[1];
          MultiturnOpticalEncoder.Eeprom.ReturnAddress = MultiturnOpticalEncoder.RxData[2];
          MultiturnOpticalEncoder.Eeprom.ReturnDNum = MultiturnOpticalEncoder.RxData[3];
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, (MultiturnOpticalEncoder.Eeprom.ReturnDNum + 4));
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[(MultiturnOpticalEncoder.Eeprom.ReturnDNum + 4)]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnOpticalEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }else{ 
            for(volatile uint16_t j=0; j<MultiturnOpticalEncoder.Eeprom.ReturnDNum; j++){
              MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.ReturnPage][MultiturnOpticalEncoder.Eeprom.ReturnAddress + j] = MultiturnOpticalEncoder.RxData[4 + j];
            }
          }
        }               
        break;
      case 0x35://写eeprom/flash功能   0x35 | PAGE | ADF1 | DNUM | DAT0  | … | DAT(N-1) | CRC
        if(MultiturnOpticalEncoder.RxDataCnt==(MultiturnOpticalEncoder.Eeprom.SetDNum + 5)){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          MultiturnOpticalEncoder.Eeprom.ReturnPage = MultiturnOpticalEncoder.RxData[1];
          MultiturnOpticalEncoder.Eeprom.ReturnAddress = MultiturnOpticalEncoder.RxData[2];
          MultiturnOpticalEncoder.Eeprom.ReturnDNum = MultiturnOpticalEncoder.RxData[3];      
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, (MultiturnOpticalEncoder.Eeprom.ReturnDNum + 4));
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[(MultiturnOpticalEncoder.Eeprom.ReturnDNum + 4)]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnOpticalEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }else{ 
            for(volatile uint16_t j=0; j<MultiturnOpticalEncoder.Eeprom.ReturnDNum; j++){
              MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.ReturnPage][MultiturnOpticalEncoder.Eeprom.ReturnAddress + j] = MultiturnOpticalEncoder.RxData[4 + j];
            }
          }
        }           
        break; 
      case 0x3D://读led光强度值、温度值、电池电压
        if(MultiturnOpticalEncoder.RxDataCnt==6){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;  
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          PNH2612.LEDReadDAC = (MultiturnOpticalEncoder.RxData[1] | (MultiturnOpticalEncoder.RxData[2] << 8))& 0xFFFF;
          MultiturnOpticalEncoder.Temperature = MultiturnOpticalEncoder.RxData[3];
          MultiturnOpticalEncoder.BatteryVoltage = MultiturnOpticalEncoder.RxData[4];
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, 5);
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[5]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnOpticalEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }
        }          
        break;
      case 0x45:
        if(MultiturnOpticalEncoder.RxDataCnt==5){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;  
          MultiturnOpticalEncoder.RxDataCnt = 0;
        }           
        break;
      case 0xCD://r值归一化值
        if(MultiturnOpticalEncoder.RxDataCnt==5){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;  
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          PNH2612.RMSQUA = MultiturnOpticalEncoder.RxData[1];
          PNH2612.RNSQUA = MultiturnOpticalEncoder.RxData[2];
          PNH2612.RSSQUA = MultiturnOpticalEncoder.RxData[3];
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, 4);
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[4]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnOpticalEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }         
        }           
        break;   
      case 0xD5://设定led光强值(DAC值)
        if(MultiturnOpticalEncoder.RxDataCnt==4){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;  
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          PNH2612.LEDDAC0 = MultiturnOpticalEncoder.RxData[1];
          PNH2612.LEDDAC1 = MultiturnOpticalEncoder.RxData[2];     
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, 3);
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[3]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnOpticalEncoder.XorCrcError;
            Work_Alarm = 0x02;
          } 
          if(MultiturnOpticalEncoder.Flag.bit.LedDac){
            MotorEncoder.TestItem = MultiturnOpticalEncoderAnalogDataTest;    
          }
        }           
        break;    
       case 0x5D:
        if(MultiturnOpticalEncoder.RxDataCnt==5){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;  
          MultiturnOpticalEncoder.RxDataCnt = 0;
        }           
        break;
      case 0xE5:
        if(MultiturnOpticalEncoder.RxDataCnt==5){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          PNH2612.Q4D = MultiturnOpticalEncoder.RxData[1];
          PNH2612.Q14D = (MultiturnOpticalEncoder.RxData[2] | (MultiturnOpticalEncoder.RxData[3] << 8))& 0xFFFF;
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, 4);
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[4]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnOpticalEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }          
        }           
        break;   
      case 0x6D:
        if(MultiturnOpticalEncoder.RxDataCnt==6){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          switch(MultiturnOpticalEncoder.IPID){
          case Encoder_ced_Test:
            MultiturnOpticalEncoder.Status0x6D = MultiturnOpticalEncoder.RxData[4];//STATUS：0 清除失败 STATUS：1 清除成功 STATUS：2 清除无效，已清除一次，不能再清除 STATUS：4 指令无效            
            break;
          case Encoder_OIP_Test:
            MultiturnOpticalEncoder.OIPStatus = MultiturnOpticalEncoder.RxData[4];
            if(MultiturnOpticalEncoder.Cnt.CFOIP == 5){
              MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;      
              MultiturnOpticalEncoder.Cnt.CFOIP = 0;
              if(MultiturnOpticalEncoder.OIPStatus == 0){
                Work_Alarm = 0x07;
              }           
            }
            if(MultiturnOpticalEncoder.OIPStatus == 4){
               Work_Alarm = 0x08;
            }            
            break;
          case Encoder_CIP_Test:
            
            break;            
          }
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, 5);
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[5]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnOpticalEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }                   
        }           
        break;  
      case 0x75:
        if(MultiturnOpticalEncoder.RxDataCnt==5){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;    
          MultiturnOpticalEncoder.RxDataCnt = 0;
          MultiturnOpticalEncoder.RxID = MultiturnOpticalEncoder.RxData[0];
          MultiturnOpticalEncoder.InternalAlarm1 = MultiturnOpticalEncoder.RxData[1];
          MultiturnOpticalEncoder.InternalAlarm2 = MultiturnOpticalEncoder.RxData[2];
          MultiturnOpticalEncoder.InternalAlarm3 = MultiturnOpticalEncoder.RxData[3];
          MultiturnOpticalEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.RxData, 4);
          if(MultiturnOpticalEncoder.XorCrcData != MultiturnOpticalEncoder.RxData[4]){
            MultiturnOpticalEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnOpticalEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }
        }           
        break;
      case 0xFD:
        if(MultiturnOpticalEncoder.RxDataCnt==5){
          UART_EnableRx(UART0, false);
          MultiturnOpticalEncoder.TimeoutCnt = 0;    
          MultiturnOpticalEncoder.RxDataCnt = 0;         
        }           
        break;         
      default:
          MultiturnOpticalEncoder.RxDataCnt = 0;
          break;              
      }
    }

}
//==============================================================================
// Encoder_TX
//==============================================================================
__ramfunc void MultiturnOpticalEncoderTX(volatile uint8_t Idle, uint8_t Addr, uint8_t Data, uint8_t LEDDAC0, uint8_t LEDDAC1)
{
  static uint8_t j = 0;
  
  switch(Idle){
  case 0x1A: //Data ID = 3, 010 1100 0, Data readout, Read all data 
      MultiturnOpticalEncoderTXOneByte(Idle);
      break;
  case 0x02: //Data ID = 0, 010 0000 0, Data readout, Read one revolution data
      MultiturnOpticalEncoderTXOneByte(Idle);
      break;
  case 0x62: //Data ID = 0, 010 0000 0, Data readout, Read one revolution data
      MultiturnOpticalEncoderTXOneByte(Idle);
      break;        
  case 0xEA: //Data ID = D, 010 1011 1, Readout from EEPROM
      MultiturnOpticalEncoder.TimeoutCnt ++;
      MultiturnOpticalEncoder.TxData[0] = Idle;                                            //CF 
      MultiturnOpticalEncoder.TxData[1] = Addr;                                            //ADF
      MultiturnOpticalEncoder.TxData[2] = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.TxData, 2);             //CRC
      uart0_transfer.data = (uint8_t *)&MultiturnOpticalEncoder.TxData[0];
      uart0_transfer.dataSize = 3;               
      Encoder485DE();                                                      //Write enabled
      for (volatile uint8_t i=0; i<5; i++);
      UART_SendDMA0(&uart0_transfer);  
    break;           
  case 0x32: //Data ID = 6, 010 0110 0, Writing to EEPROM
      MultiturnOpticalEncoder.TimeoutCnt ++;
      MultiturnOpticalEncoder.TxData[0] = Idle;                                            //CF 
      MultiturnOpticalEncoder.TxData[1] = Addr;                                            //ADF
      MultiturnOpticalEncoder.TxData[2] = Data;                                            //EDF
      MultiturnOpticalEncoder.TxData[3] = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.TxData, 3);             //CRC
      uart0_transfer.data = (uint8_t *)&MultiturnOpticalEncoder.TxData[0];
      uart0_transfer.dataSize = 4;               
      Encoder485DE();                                                      //Write enabled
      for (volatile uint8_t i=0; i<5; i++);                          
      UART_SendDMA0(&uart0_transfer);
     break; 
    case 0x85:
      MultiturnOpticalEncoderTXOneByte(Idle);
      break;      
    case 0x0D:
      MultiturnOpticalEncoderTXOneByte(Idle);
      break;      
    case 0x15:
      MultiturnOpticalEncoderTXOneByte(Idle);
      break;        
    case 0x9D:
      MultiturnOpticalEncoderTXOneByte(Idle);
      break;
    case 0x25://读取当前位置值及Hall逻辑电平值、MTAB逻辑电平
      MultiturnOpticalEncoderTXOneByte(Idle);  
      break;
    case 0xAD://读eeprom/flash功能 0xAD  | PAGE | ADF1 | DNUM | CRC
      MultiturnOpticalEncoder.TimeoutCnt ++;
      MultiturnOpticalEncoder.TxData[0] = Idle;                                                 
      MultiturnOpticalEncoder.TxData[1] = MultiturnOpticalEncoder.Eeprom.SetPage;         
      MultiturnOpticalEncoder.TxData[2] = MultiturnOpticalEncoder.Eeprom.SetAddress;
      MultiturnOpticalEncoder.TxData[3] = MultiturnOpticalEncoder.Eeprom.SetDNum;
      MultiturnOpticalEncoder.TxData[4] = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.TxData, 4);                 //CRC          
      uart0_transfer.data = (uint8_t *)&MultiturnOpticalEncoder.TxData[0];
      uart0_transfer.dataSize = 5;           
      Encoder485DE();                                                        
      for (volatile uint8_t i=0; i<5; i++);
      UART_SendDMA0(&uart0_transfer);          
      break;
    case 0x35://写eeprom/flash功能   0x35 | PAGE | ADF1 | DNUM | DAT0  | … | DAT(N-1) | CRC
      MultiturnOpticalEncoder.TimeoutCnt ++;
      MultiturnOpticalEncoder.TxData[0] = Idle;                                                //CF                 
      MultiturnOpticalEncoder.TxData[1] = MultiturnOpticalEncoder.Eeprom.SetPage; 
      MultiturnOpticalEncoder.TxData[2] = MultiturnOpticalEncoder.Eeprom.SetAddress; 
      MultiturnOpticalEncoder.TxData[3] = MultiturnOpticalEncoder.Eeprom.SetDNum;
      for(j=0; j<MultiturnOpticalEncoder.Eeprom.SetDNum; j++){
        MultiturnOpticalEncoder.TxData[4+j] = MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.SetPage][MultiturnOpticalEncoder.Eeprom.SetAddress+j];
      }
      MultiturnOpticalEncoder.TxData[4+j] = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.TxData, (4+j));     
      uart0_transfer.data = (uint8_t *)&MultiturnOpticalEncoder.TxData[0];
      uart0_transfer.dataSize = (5+j);           
      Encoder485DE();                                                          //Write enabled
      for (volatile uint8_t i=0; i<5; i++);
      UART_SendDMA0(&uart0_transfer);          
      break; 
    case 0x3D://读led光强度值、温度值、电池电压
      MultiturnOpticalEncoderTXOneByte(Idle);   
      break;
    case 0x45:
        
      break;
    case 0xCD://r值归一化值
      MultiturnOpticalEncoderTXOneByte(Idle);  
      break;   
    case 0xD5://设定led光强值(DAC值)
      MultiturnOpticalEncoder.TimeoutCnt ++;
      MultiturnOpticalEncoder.TxData[0] = Idle;                                                //CF  
      MultiturnOpticalEncoder.TxData[1] = LEDDAC0;                                                //DAC0   
      MultiturnOpticalEncoder.TxData[2] = LEDDAC1;                                                //DAC1   
      MultiturnOpticalEncoder.TxData[3] = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.TxData, 3);                 //CRC          
      uart0_transfer.data = (uint8_t *)&MultiturnOpticalEncoder.TxData[0];
      uart0_transfer.dataSize = 4;           
      Encoder485DE();                                                          //Write enabled
      for (volatile uint8_t i=0; i<5; i++);
      UART_SendDMA0(&uart0_transfer);          
      break;    
     case 0x5D:
       
      break;
    case 0xE5://获取阈值补偿值
      MultiturnOpticalEncoderTXOneByte(Idle); 
      break;   
    case 0x6D://clear eeprom data  该指令只能生效一次
      MultiturnOpticalEncoder.TimeoutCnt ++;
      if(Data == Encoder_ced_Test){
        MultiturnOpticalEncoder.IPID = Data;
        MultiturnOpticalEncoder.TxData[0] = Idle;                                                //CF                 
        MultiturnOpticalEncoder.TxData[1] = 0x63; //'c'
        MultiturnOpticalEncoder.TxData[2] = 0x65; //'e'
        MultiturnOpticalEncoder.TxData[3] = 0x64; //'d'      
      }else if(Data == Encoder_CIP_Test){
        MultiturnOpticalEncoder.IPID = Data;
        MultiturnOpticalEncoder.TxData[0] = Idle;                                                //CF                 
        MultiturnOpticalEncoder.TxData[1] = 0x43; //'C'
        MultiturnOpticalEncoder.TxData[2] = 0x49; //'I'
        MultiturnOpticalEncoder.TxData[3] = 0x50; //'P'            
      }else if(Data == Encoder_OIP_Test){
        MultiturnOpticalEncoder.IPID = Data;
        MultiturnOpticalEncoder.TxData[0] = Idle;                                                //CF                 
        MultiturnOpticalEncoder.TxData[1] = 0x4F; //'O'
        MultiturnOpticalEncoder.TxData[2] = 0x49; //'I'
        MultiturnOpticalEncoder.TxData[3] = 0x50; //'P'         
      }                                       
      MultiturnOpticalEncoder.TxData[4] = CRC8_Check((uint8_t *)MultiturnOpticalEncoder.TxData, 4);                 //CRC          
      uart0_transfer.data = (uint8_t *)&MultiturnOpticalEncoder.TxData[0];
      uart0_transfer.dataSize = 5;           
      Encoder485DE();                                                      
      for (volatile uint8_t i=0; i<5; i++);
      UART_SendDMA0(&uart0_transfer);         
      break;  
    case 0x75://读取报警状态
      MultiturnOpticalEncoderTXOneByte(Idle);  
      break;
    case 0xFD:
    
      break;        
  default:

      break;
  }

  if(MultiturnOpticalEncoder.TimeoutCnt > 5){
    ModBus.Error.bit.DC = 1;
    Work_Alarm = 0x01;
  }         

}


void MNS_SinCos_MaxMin(void)
{
/*Sin Max Min */  
    if(PNH2612.M.SinData > PNH2612.M.SinDataMax){
      PNH2612.M.SinDataMax = PNH2612.M.SinData;
    }
    if(PNH2612.M.SinData < PNH2612.M.SinDataMin){
      PNH2612.M.SinDataMin = PNH2612.M.SinData;
    }          
    if(PNH2612.N.SinData > PNH2612.N.SinDataMax){
      PNH2612.N.SinDataMax = PNH2612.N.SinData;
    }
    if(PNH2612.N.SinData < PNH2612.N.SinDataMin){
      PNH2612.N.SinDataMin = PNH2612.N.SinData;
    }
    if(PNH2612.S.SinData > PNH2612.S.SinDataMax){
      PNH2612.S.SinDataMax = PNH2612.S.SinData;
    }
    if(PNH2612.S.SinData < PNH2612.S.SinDataMin){
      PNH2612.S.SinDataMin = PNH2612.S.SinData;
    }
/*Cos Max Min */
    if(PNH2612.M.CosData > PNH2612.M.CosDataMax){
      PNH2612.M.CosDataMax = PNH2612.M.CosData;
    }
    if(PNH2612.M.CosData < PNH2612.M.CosDataMin){
      PNH2612.M.CosDataMin = PNH2612.M.CosData;
    }          
    if(PNH2612.N.CosData > PNH2612.N.CosDataMax){
      PNH2612.N.CosDataMax = PNH2612.N.CosData;
    }
    if(PNH2612.N.CosData < PNH2612.N.CosDataMin){
      PNH2612.N.CosDataMin = PNH2612.N.CosData;
    }
    if(PNH2612.S.CosData > PNH2612.S.CosDataMax){
      PNH2612.S.CosDataMax = PNH2612.S.CosData;
    }
    if(PNH2612.S.CosData < PNH2612.S.CosDataMin){
      PNH2612.S.CosDataMin = PNH2612.S.CosData;
    }        
}
//==============================================================================
// MultiturnOpticalEncoderLedDac
//==============================================================================
void MultiturnOpticalEncoderLedDac(void)
{
    if(MultiturnOpticalEncoder.Flag.bit.LedDac){
      MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;
      PNH2612.MSinDataBuffer[PNH2612.LEDTestDACCnt] = PNH2612.M.SinData;
      PNH2612.LEDTestDACCnt ++;
      if(PNH2612.LEDTestDACCnt >= 1){    
        if(PNH2612.LEDTestDACCnt > 1){
          if(PNH2612.LEDTestDACCnt == 6){
            PNH2612.LEDTestDACResult = 0x02;//2失败
            MultiturnOpticalEncoder.Flag.bit.LedDac = 0;
          }else{
            if(PNH2612.MSinDataBuffer[PNH2612.LEDTestDACCnt - 2] != PNH2612.MSinDataBuffer[PNH2612.LEDTestDACCnt - 1]){
              PNH2612.LEDTestDACResult = 0x01;//1成功
              MultiturnOpticalEncoder.Flag.bit.LedDac = 0;
            }else{
              MotorEncoder.TestItem = MultiturnOpticalEncoderLightIntensityTest;
            }
          }
        }else{
          MotorEncoder.TestItem = MultiturnOpticalEncoderLightIntensityTest;
        }
      }
    }  
}
//==============================================================================
// MultiturnOpticalEncoderLedDac
//==============================================================================
void MultiturnOpticalEncoderSectorCollect(void)
{
    if(MultiturnOpticalEncoder.Flag.bit.MTABHALL == 1){
      MultiturnOpticalEncoder.Hall.Buffer[0] = PNH2612.HallSector;
      MultiturnOpticalEncoder.MTAB.Buffer[0] = PNH2612.MTABSector;
      MultiturnOpticalEncoder.Flag.bit.MTABHALL = 0;
    }else if(MultiturnOpticalEncoder.Flag.bit.MTABHALL == 2){
      MultiturnOpticalEncoder.Hall.Buffer[1] = PNH2612.HallSector;
      MultiturnOpticalEncoder.MTAB.Buffer[1] = PNH2612.MTABSector; 
      MultiturnOpticalEncoder.Flag.bit.MTABHALL = 0;
    }else if(MultiturnOpticalEncoder.Flag.bit.MTABHALL == 3){
      MultiturnOpticalEncoder.Hall.Buffer[2] = PNH2612.HallSector;
      MultiturnOpticalEncoder.MTAB.Buffer[2] = PNH2612.MTABSector;  
      MultiturnOpticalEncoder.Flag.bit.MTABHALL = 0;
    }else if(MultiturnOpticalEncoder.Flag.bit.MTABHALL == 4){
      MultiturnOpticalEncoder.Hall.Buffer[3] = PNH2612.HallSector;
      MultiturnOpticalEncoder.MTAB.Buffer[3] = PNH2612.MTABSector;  
      MultiturnOpticalEncoder.Flag.bit.MTABHALL = 0;
    }  
}
//==============================================================================
// MultiturnOpticalEncoderReadHWRev
//==============================================================================
void MultiturnOpticalEncoderReadHWRev(void)
{
  MotorEncoder.HWRev[0] = MultiturnOpticalEncoder.Eeprom.DataBuffer[2][0x70];
  MotorEncoder.HWRev[1] = '.';
  MotorEncoder.HWRev[2] = MultiturnOpticalEncoder.Eeprom.DataBuffer[2][0x71];
  MotorEncoder.HWRev[3] = '.';
  MotorEncoder.HWRev[4] = MultiturnOpticalEncoder.Eeprom.DataBuffer[2][0x72] + 0x30;
  MotorEncoder.HWRev[5] = '.';
  MotorEncoder.HWRev[6] = MultiturnOpticalEncoder.Eeprom.DataBuffer[2][0x73] + 0x30;
  MotorEncoder.HWRev[7] = '\0';
  hexToAsciiString(MotorEncoder.HWRev, MotorEncoder.HWRevBuffer, 7);
}
//==============================================================================
// MultiturnMagneticEncoderReadFWRev
//==============================================================================
void MultiturnOpticalEncoderReadFWRev(void)
{
  MotorEncoder.FWRev[0] = MultiturnOpticalEncoder.Eeprom.DataBuffer[3][20] + 0x30;
  MotorEncoder.FWRev[1] = '.';
  MotorEncoder.FWRev[2] = MultiturnOpticalEncoder.Eeprom.DataBuffer[3][21] + 0x30;
  MotorEncoder.FWRev[3] = '.';
  MotorEncoder.FWRev[4] = MultiturnOpticalEncoder.Eeprom.DataBuffer[3][22] + 0x30;
  MotorEncoder.FWRev[5] = '.';
  MotorEncoder.FWRev[6] = MultiturnOpticalEncoder.Eeprom.DataBuffer[3][23];
  MotorEncoder.FWRev[7] = '\0';
  hexToAsciiString(MotorEncoder.FWRev, MotorEncoder.FWRevBuffer, 7);
}
//==============================================================================
// MultiturnOpticalEncoderReadAllEeprom
//==============================================================================
void MultiturnOpticalEncoderReadAllEeprom(void)
{
  if(MultiturnOpticalEncoder.Eeprom.SetPage < MultiturnOpticalEncoderPageNumber){  //1ms 一个周期，4页 4ms读完
    MultiturnOpticalEncoder.Eeprom.SetDNum = 0x80;
    MultiturnOpticalEncoder.Eeprom.SetAddress = 0x00;
    MultiturnOpticalEncoderTX(0xAD, 0x00, 0x00, 0x00, 0x00);         
    MultiturnOpticalEncoder.Eeprom.SetPage ++;  
  }else{
    MultiturnOpticalEncoderReadHWRev();
    MultiturnOpticalEncoderReadFWRev();    
    MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;
  }
}
//==============================================================================
// MultiturnOpticalEncoderMultiturnReset
//==============================================================================
void MultiturnOpticalEncoderMultiturnReset(void)
{
  if(MultiturnOpticalEncoder.Cnt.CF62 < 10){
    MultiturnOpticalEncoderTX(0x62, 0x00, 0x00, 0x00, 0x00);
    MultiturnOpticalEncoder.Cnt.CF62 ++;
    if(MultiturnOpticalEncoder.Cnt.CF62 == 10){
      MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;
    }
  }  
}
//==============================================================================
// MultiturnOpticalEncoderOpenInternalProtocol
//==============================================================================
void MultiturnOpticalEncoderOpenInternalProtocol(void)
{
  if(MultiturnOpticalEncoder.Cnt.CFOIP < 5){
    MultiturnOpticalEncoderTX(0x6D, 0x00,Encoder_OIP_Test,0x00,0x00); 
    MultiturnOpticalEncoder.Cnt.CFOIP ++;
  }else{
    MultiturnOpticalEncoder.Cnt.CFOIP = 0;
    MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;       
  }
}
//==============================================================================
// MultiturnOpticalEncoderInitialize
//==============================================================================
void MultiturnOpticalEncoderInitialize(void)
{
  if(MultiturnOpticalEncoder.Cnt.CFced < 5){
    MultiturnOpticalEncoderTX(0x6D, 0x00,Encoder_ced_Test,0x00,0x00); 
    MultiturnOpticalEncoder.Cnt.CFced ++;
  }else{
    MultiturnOpticalEncoder.Cnt.CFced = 0;
    MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;    
  }
}
//==============================================================================
// MultiturnOpticalEncoderWriteResult
//==============================================================================
void MultiturnOpticalEncoderWriteResult(void)
{
  MultiturnOpticalEncoder.Eeprom.SetPage = 0x02;
  MultiturnOpticalEncoder.Eeprom.SetAddress = 0x00;
  MultiturnOpticalEncoder.Eeprom.SetDNum = 0x01;
  MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.SetPage][MultiturnOpticalEncoder.Eeprom.SetAddress] = MultiturnOpticalEncoder.TestResult; //9代表整机测试和PCBA测试完成，1代表PCBA测试完成
  MultiturnOpticalEncoderTX(0x35, 0x00, 0x00, 0x00, 0x00); 
  MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;
}
//==============================================================================
// MultiturnOpticalEncoderGetAllData
//==============================================================================
void MultiturnOpticalEncoderGetAllData(void)
{
  MultiturnOpticalEncoderTX(0x1A, 0x00, 0x00, 0x00, 0x00);
  MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;
}
//==============================================================================
// MultiturnOpticalEncoderTB
//==============================================================================
void MultiturnOpticalEncoderTB(void)
{
  MultiturnOpticalEncoderTX(0x3D, 0x00, 0x00, 0x00, 0x00);
  MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;  
}
//==============================================================================
// MultiturnOpticalEncoderDAC
//==============================================================================
void MultiturnOpticalEncoderDAC(void)
{
  PNH2612.LEDDAC0 = PNH2612.LEDTestDAC & 0xFF;
  PNH2612.LEDDAC1 = (PNH2612.LEDTestDAC >> 8) & 0xFF;
  MultiturnOpticalEncoderTX(0xD5, 0x00, 0x00, PNH2612.LEDDAC0, PNH2612.LEDDAC1);
  MotorEncoder.TestItem = MultiturnOpticalEncoderReadAnalogDataTest;  
}
//==============================================================================
// MultiturnOpticalEncoderLightIntensity
//==============================================================================
void MultiturnOpticalEncoderLightIntensity(void)
{
  if(MultiturnOpticalEncoder.Flag.bit.LedDac){
    PNH2612.LEDTestDAC = (1950 - 50 * PNH2612.LEDTestDACCnt);
  }
  PNH2612.LEDDAC0 = PNH2612.LEDTestDAC & 0xFF;
  PNH2612.LEDDAC1 = (PNH2612.LEDTestDAC >> 8) & 0xFF;
  MultiturnOpticalEncoderTX(0xD5, 0x00, 0x00, PNH2612.LEDDAC0, PNH2612.LEDDAC1); 
  MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;  
}
//==============================================================================
// MultiturnOpticalAnalogReset
//==============================================================================
void MultiturnOpticalAnalogReset(void)
{
  PNH2612.M.SinDataMax = 0;
  PNH2612.M.CosDataMax = 0;
  PNH2612.N.SinDataMax = 0;
  PNH2612.N.CosDataMax = 0;
  PNH2612.S.SinDataMax = 0;
  PNH2612.S.CosDataMax = 0;
}
//==============================================================================
// MultiturnOpticalEncoderMNSAnalogMaxCheck
// 先判断测扇区时的模拟量最大值是否满足
//==============================================================================
void MultiturnOpticalEncoderMNSAnalogMaxCheck(void)
{
  if(
  // 判断所有变量是否在3100到3800之间
    (PNH2612.M.SinDataMax >= 3100 && PNH2612.M.SinDataMax <= 3800) &&
    (PNH2612.M.CosDataMax >= 3100 && PNH2612.M.CosDataMax <= 3800) &&
    (PNH2612.N.SinDataMax >= 3100 && PNH2612.N.SinDataMax <= 3800) &&
    (PNH2612.N.CosDataMax >= 3100 && PNH2612.N.CosDataMax <= 3800) &&
    (PNH2612.S.SinDataMax >= 3100 && PNH2612.S.SinDataMax <= 3800) &&
    (PNH2612.S.CosDataMax >= 3100 && PNH2612.S.CosDataMax <= 3800) &&
    // 判断差值的绝对值是否小于100
    (abs(PNH2612.M.SinDataMax - PNH2612.M.CosDataMax) < 100) &&
    (abs(PNH2612.N.SinDataMax - PNH2612.N.CosDataMax) < 100) &&
    (abs(PNH2612.S.SinDataMax - PNH2612.S.CosDataMax) < 100)     
  ){
    if(PNH2612.LEDAdjustDACCnt){//代表是调节后才达到，则需要再进行转一圈判断max值
      if(MultiturnOpticalEncoder.Flag.bit.MNSAMDOneLapCheck == 2){
        PNH2612.MNSAnalogResult = 4;//代表调节后成功
        MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;
      }else{
        MultiturnOpticalAnalogReset();
        MultiturnOpticalEncoder.Flag.bit.MNSAMDOneLapCheck = 1;
        MotorEncoder.TestItem = MultiturnOpticalEncoderAnalogDataTest;
      }
    }else{
      PNH2612.MNSAnalogResult = 1;//代表一次成功
      MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;
    }
  }else{
    if(
       (PNH2612.M.SinDataMax < 3100 || PNH2612.M.CosDataMax < 3100) ||
       (PNH2612.N.SinDataMax < 3100 || PNH2612.N.CosDataMax < 3100) ||
       (PNH2612.S.SinDataMax < 3100 || PNH2612.S.CosDataMax < 3100)        
    ){
      PNH2612.LEDAdjustDACData = 50;
    }else if(
       (PNH2612.M.SinDataMax > 3800 || PNH2612.M.CosDataMax > 3800) ||
       (PNH2612.N.SinDataMax > 3800 || PNH2612.N.CosDataMax > 3800) ||
       (PNH2612.S.SinDataMax > 3800 || PNH2612.S.CosDataMax > 3800)               
    ){
      PNH2612.LEDAdjustDACData = -50;
    }
    PNH2612.MNSAnalogResult = 2;//代表调节中
    MultiturnOpticalAnalogReset();
    MultiturnOpticalEncoder.Flag.bit.LedDacAdjust = 1;
    MotorEncoder.TestItem = MultiturnOpticalEncoderDACAdjustmentTest;
  }
//  if(PNH2612.MNSAnalogResult == 2){
//    MultiturnOpticalAnalogReset();
//    MultiturnOpticalEncoder.Flag.bit.LedDacAdjust = 1;
//    MotorEncoder.TestItem = MultiturnOpticalEncoderDACAdjustmentTest;
//  }  
}
//==============================================================================
// MultiturnOpticalEncoderDACAdjustment
//==============================================================================
void MultiturnOpticalEncoderDACAdjustment(void)
{  
  if(MultiturnOpticalEncoder.Flag.bit.LedDacAdjust){
    if(PNH2612.LEDAdjustDACCnt < 10){
      PNH2612.LEDAdjustDAC = (1872 + (PNH2612.LEDAdjustDACData * PNH2612.LEDAdjustDACCnt));//默认DAC是1922
      PNH2612.LEDAdjustDACCnt ++;    
      PNH2612.LEDDAC0 = PNH2612.LEDAdjustDAC & 0xFF;
      PNH2612.LEDDAC1 = (PNH2612.LEDAdjustDAC >> 8) & 0xFF;
      MultiturnOpticalEncoderTX(0xD5, 0x00, 0x00, PNH2612.LEDDAC0, PNH2612.LEDDAC1); 
      MultiturnOpticalEncoder.Flag.bit.LedDacAdjust = 0;
    }else{
      PNH2612.MNSAnalogResult = 3;//代表调节不成功
      //PNH2612.LEDAdjustDACCnt = 0;
      MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;
      return;
    }
  }
  if(PNH2612.MNSAnalogWaitCnt < 255){
    PNH2612.MNSAnalogWaitCnt ++;
  }else{
    PNH2612.MNSAnalogWaitCnt = 0;
    MotorEncoder.TestItem = MultiturnOpticalEncoderAnalogDataTest;
  }
}
//==============================================================================
// MultiturnOpticalEncoderWriteDate
//==============================================================================
void MultiturnOpticalEncoderWriteDate(void)
{
  MultiturnOpticalEncoder.Eeprom.SetPage = 0x02;
  MultiturnOpticalEncoder.Eeprom.SetAddress = 0x68;
  MultiturnOpticalEncoder.Eeprom.SetDNum = 0x04;
  MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.SetPage][MultiturnOpticalEncoder.Eeprom.SetAddress] = MotorEncoder.TestYear;
  MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.SetPage][MultiturnOpticalEncoder.Eeprom.SetAddress+1] = MotorEncoder.TestMoon;
  MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.SetPage][MultiturnOpticalEncoder.Eeprom.SetAddress+2] = MotorEncoder.TestDay;
  MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.SetPage][MultiturnOpticalEncoder.Eeprom.SetAddress+3] = MotorEncoder.TestHour;
  MultiturnOpticalEncoderTX(0x35, 0x00, 0x00, 0x00, 0x00); 
  MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;
}
//==============================================================================
// MultiturnOpticalEncoderWriteRMRNRS
//==============================================================================
void MultiturnOpticalEncoderWriteRMRNRS(void)
{
  MultiturnOpticalEncoder.Eeprom.SetPage = 0x02;
  MultiturnOpticalEncoder.Eeprom.SetAddress = 0x58;
  MultiturnOpticalEncoder.Eeprom.SetDNum = 0x06;
  MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.SetPage][MultiturnOpticalEncoder.Eeprom.SetAddress] = 90;
  MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.SetPage][MultiturnOpticalEncoder.Eeprom.SetAddress+1] = 0;
  MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.SetPage][MultiturnOpticalEncoder.Eeprom.SetAddress+2] = 90;
  MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.SetPage][MultiturnOpticalEncoder.Eeprom.SetAddress+3] = 0;
  MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.SetPage][MultiturnOpticalEncoder.Eeprom.SetAddress+4] = 90;
  MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.SetPage][MultiturnOpticalEncoder.Eeprom.SetAddress+5] = 0;
  MultiturnOpticalEncoderTX(0x35, 0x00, 0x00, 0x00, 0x00); 
  MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;
}
//==============================================================================
// MultiturnOpticalEncoderWriteHWRevTest
//==============================================================================
void MultiturnOpticalEncoderWriteHWRev(void)
{
  MultiturnOpticalEncoder.Eeprom.SetPage = 0x02;
  MultiturnOpticalEncoder.Eeprom.SetAddress = 0x70;
  MultiturnOpticalEncoder.Eeprom.SetDNum = 0x04;
  MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.SetPage][MultiturnOpticalEncoder.Eeprom.SetAddress] = 'H';
  MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.SetPage][MultiturnOpticalEncoder.Eeprom.SetAddress+1] = 'O';
  MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.SetPage][MultiturnOpticalEncoder.Eeprom.SetAddress+2] = 1;
  MultiturnOpticalEncoder.Eeprom.DataBuffer[MultiturnOpticalEncoder.Eeprom.SetPage][MultiturnOpticalEncoder.Eeprom.SetAddress+3] = MotorEncoder.HWRevData;
  MultiturnOpticalEncoderTX(0x35, 0x00, 0x00, 0x00, 0x00);  
  MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;
}

//==============================================================================
// MultiturnMagneticEncoderHallCheck
//==============================================================================
void MultiturnOpticalEncoderHallCheck(void)
{
    switch(MultiturnOpticalEncoder.Hall.Buffer[0]){
    case 0x00:
      if(MultiturnOpticalEncoder.Hall.Buffer[1] == 3 && MultiturnOpticalEncoder.Hall.Buffer[2] == 2 && MultiturnOpticalEncoder.Hall.Buffer[3] == 1){
        MultiturnOpticalEncoder.Hall.Result = 1;        
      }else{
        MultiturnOpticalEncoder.Hall.Result = 0;
      }
      break;
    case 0x01:
      if(MultiturnOpticalEncoder.Hall.Buffer[1] == 0 && MultiturnOpticalEncoder.Hall.Buffer[2] == 3 && MultiturnOpticalEncoder.Hall.Buffer[3] == 2){
        MultiturnOpticalEncoder.Hall.Result = 1;        
      }else{
        MultiturnOpticalEncoder.Hall.Result = 0;
      } 
      break;
    case 0x02:
      if(MultiturnOpticalEncoder.Hall.Buffer[1] == 1 && MultiturnOpticalEncoder.Hall.Buffer[2] == 0 && MultiturnOpticalEncoder.Hall.Buffer[3] == 3){
        MultiturnOpticalEncoder.Hall.Result = 1;
      }else{
        MultiturnOpticalEncoder.Hall.Result = 0;
      }       
      break;
    case 0x03:
      if(MultiturnOpticalEncoder.Hall.Buffer[1] == 2 && MultiturnOpticalEncoder.Hall.Buffer[2] == 1 && MultiturnOpticalEncoder.Hall.Buffer[3] == 0){
        MultiturnOpticalEncoder.Hall.Result = 1;
      }else{
        MultiturnOpticalEncoder.Hall.Result = 0;
      }   
      break;
    }      
}
//==============================================================================
// MultiturnMagneticEncoderMTABCheck
//==============================================================================
void MultiturnOpticalEncoderMTABCheck(void)
{
    switch(MultiturnOpticalEncoder.MTAB.Buffer[0]){
    case 0x00:
      if(MultiturnOpticalEncoder.MTAB.Buffer[1] == 1 && MultiturnOpticalEncoder.MTAB.Buffer[2] == 3 && MultiturnOpticalEncoder.MTAB.Buffer[3] == 2){
        MultiturnOpticalEncoder.MTAB.Result = 1;        
      }else{
        MultiturnOpticalEncoder.MTAB.Result = 0;
      }
      break;
    case 0x01:
      if(MultiturnOpticalEncoder.MTAB.Buffer[1] == 3 && MultiturnOpticalEncoder.MTAB.Buffer[2] == 2 && MultiturnOpticalEncoder.MTAB.Buffer[3] == 0){
        MultiturnOpticalEncoder.MTAB.Result = 1;        
      }else{
        MultiturnOpticalEncoder.MTAB.Result = 0;
      } 
      break;
    case 0x02:
      if(MultiturnOpticalEncoder.MTAB.Buffer[1] == 0 && MultiturnOpticalEncoder.MTAB.Buffer[2] == 1 && MultiturnOpticalEncoder.MTAB.Buffer[3] == 3){
        MultiturnOpticalEncoder.MTAB.Result = 1;
      }else{
        MultiturnOpticalEncoder.MTAB.Result = 0;
      }       
      break;
    case 0x03:
      if(MultiturnOpticalEncoder.MTAB.Buffer[1] == 2 && MultiturnOpticalEncoder.MTAB.Buffer[2] == 0 && MultiturnOpticalEncoder.MTAB.Buffer[3] == 1){
        MultiturnOpticalEncoder.MTAB.Result = 1;
      }else{
        MultiturnOpticalEncoder.MTAB.Result = 0;
      }   
      break;
    }      
}
//==============================================================================
// MultiturnOpticalEncoderMNSSpeedCheck
//==============================================================================
void MultiturnOpticalEncoderMNSSpeedCheck(void)
{
  PNH2612.M.AbsoluteBuffer[1] = PNH2612.M.AbsoluteBuffer[0];
  PNH2612.M.AbsoluteBuffer[0] = PNH2612.M.Absolute;
  PNH2612.M.AbsoluteDifference = PNH2612.M.AbsoluteBuffer[0] - PNH2612.M.AbsoluteBuffer[1];
  
  PNH2612.N.AbsoluteBuffer[1] = PNH2612.N.AbsoluteBuffer[0];
  PNH2612.N.AbsoluteBuffer[0] = PNH2612.N.Absolute;
  PNH2612.N.AbsoluteDifference = PNH2612.N.AbsoluteBuffer[0] - PNH2612.N.AbsoluteBuffer[1];
  
  PNH2612.S.AbsoluteBuffer[1] = PNH2612.S.AbsoluteBuffer[0];
  PNH2612.S.AbsoluteBuffer[0] = PNH2612.S.Absolute; 
  PNH2612.S.AbsoluteDifference = PNH2612.S.AbsoluteBuffer[0] - PNH2612.S.AbsoluteBuffer[1];
  
  if(PNH2612.M.AbsoluteDifference > 16384){
    PNH2612.M.AbsoluteDifference -= 32768;
  }else if(PNH2612.M.AbsoluteDifference < -16384){
    PNH2612.M.AbsoluteDifference += 32768;
  }
  if(PNH2612.N.AbsoluteDifference > 16384){
    PNH2612.N.AbsoluteDifference -= 32768;
  }else if(PNH2612.N.AbsoluteDifference < -16384){
    PNH2612.N.AbsoluteDifference += 32768;
  }
  if(PNH2612.S.AbsoluteDifference > 16384){
    PNH2612.S.AbsoluteDifference -= 32768;
  }else if(PNH2612.S.AbsoluteDifference < -16384){
    PNH2612.S.AbsoluteDifference += 32768;
  }  
  
//  PNH2612.M.Speed = ((PNH2612.M.AbsoluteDifference * 60 * 8000) >> 15) >> 9;
  PNH2612.M.Speed = (PNH2612.M.AbsoluteDifference * 1875) >> 16;
  PNH2612.N.Speed = (PNH2612.M.AbsoluteDifference * 1875) >> 16;
  PNH2612.S.Speed = (PNH2612.M.AbsoluteDifference * 1875) >> 16;
  
  if(PNH2612.SamplingCnt < 16000){
    PNH2612.SamplingCnt ++;
    if(PNH2612.SamplingCnt > 2){
      if(PNH2612.M.SpeedFlag == 0){
        if(PNH2612.M.Speed > 70 || PNH2612.M.Speed < 50){
          PNH2612.M.SpeedResult = 2;
          PNH2612.M.FeedbackSpeed = PNH2612.M.Speed;
          PNH2612.M.SpeedFlag = 1;
        }else{
          PNH2612.M.SpeedResult = 1;
          PNH2612.M.FeedbackSpeed = PNH2612.M.Speed;
        }    
      }

      if(PNH2612.N.SpeedFlag == 0){
        if(PNH2612.N.Speed > 70 || PNH2612.N.Speed < 50){
          PNH2612.N.SpeedResult = 2;
          PNH2612.N.FeedbackSpeed = PNH2612.N.Speed;
          PNH2612.N.SpeedFlag = 1;
        }else{
          PNH2612.N.SpeedResult = 1;
          PNH2612.N.FeedbackSpeed = PNH2612.N.Speed;
        }    
      }
      
      if(PNH2612.S.SpeedFlag == 0){
        if(PNH2612.S.Speed > 70 || PNH2612.S.Speed < 50){
          PNH2612.S.SpeedResult = 2;
          PNH2612.S.FeedbackSpeed = PNH2612.S.Speed;
          PNH2612.N.SpeedFlag = 1;
        }else{
          PNH2612.S.SpeedResult = 1;
          PNH2612.S.FeedbackSpeed = PNH2612.S.Speed;
        }    
      }
    }
  }
}
//==============================================================================
// MultiturnOpticalEncoderMPositionMark
//==============================================================================
void MultiturnOpticalEncoderMPositionMark(void)
{  
  if(PNH2612.M.PositionFlag == 1){
    PNH2612.M.MarkPositionBuffer[1] = PNH2612.M.MarkPositionBuffer[0];  
    PNH2612.M.MarkPositionBuffer[0] = PNH2612.M.Absolute;   
    Motor.FctPos_MPos_Diff[0] = (Motor.FctPosition >> 9) - (PNH2612.M.Absolute >> 1);
    PNH2612.M.PositionFlag = 2;
  }else if(PNH2612.M.PositionFlag == 3){
    PNH2612.M.MarkPositionBuffer[1] = PNH2612.M.MarkPositionBuffer[0];  
    PNH2612.M.MarkPositionBuffer[0] = PNH2612.M.Absolute;   
    PNH2612.M.MarkPositionDifference = abs(PNH2612.M.MarkPositionBuffer[1] - PNH2612.M.MarkPositionBuffer[0]);
    Motor.FctPos_MPos_Diff[1] = ((Motor.FctPosition - 8388608) >> 9) - (PNH2612.M.Absolute >> 1);
    PNH2612.M.PositionFlag = 0;
  } 
}
void MultiturnOpticalEncoderMPositionMark1(void)
{  
  static uint8_t i = 0;
  if(PNH2612.M.PositionFlag == 1){
    if(i < 2){
      i ++;      
    }else{
      PNH2612.M.PositionFlag = 2; 
    }
    Motor.FctPos_MPos_Diff[0] = Motor.FctPosition - MultiturnOpticalEncoder.SingleTurnPosition;
  }else if(PNH2612.M.PositionFlag == 3){
    Motor.FctPos_MPos_Diff[1] = Motor.FctPosition - 8388608 - MultiturnOpticalEncoder.SingleTurnPosition;
    PNH2612.M.PositionFlag = 0;
    MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;
  } 
}
//==============================================================================
// 函数名称：MultiturnOpticalEncoderMTABContinuousCheck
// 函数功能：MTAB 连续采样检测 (无Reset版，支持错误累计)
//==============================================================================
void MultiturnOpticalEncoderMTABContinuousCheck(void)
{
    // 利用 static 的默认初始化特性 (重启后为 0 或 指定值)
    static uint8_t prev_logic  = 0xFF;
    static uint8_t start_logic = 0xFF;
    static uint8_t change_cnt  = 0;
    static uint8_t circle_done = 0;

    uint8_t curr_phys, curr_logic, diff;

    // 如果一圈已经结束，停止更新，保持现场供上位机读取
    if(circle_done) return;

    // 1. 读取并映射
    curr_phys = PNH2612.MTABSector;
    curr_logic = MTAB_Map[curr_phys & 0x03];

    // 2. 上电第一次初始化
    if(prev_logic == 0xFF)
    {
        prev_logic  = curr_logic;
        start_logic = curr_logic;
        change_cnt  = 0;
        circle_done = 0;
        
        // 确保结构体变量在重启后被正确初始化
        MultiturnOpticalEncoder.MTAB.Result      = 0;
        MultiturnOpticalEncoder.MTAB.Check       = ENC_STATUS_TESTING;
        MultiturnOpticalEncoder.MTAB.Cnt         = 0;
        MultiturnOpticalEncoder.MTAB.GlitchCnt   = 0;
        MultiturnOpticalEncoder.MTAB.JitterCnt   = 0;
        MultiturnOpticalEncoder.MTAB.CountErrCnt = 0;
        return;
    }

    // 3. 无变化退出
    if(curr_logic == prev_logic) return;

    // 4. 计算差值
    diff = (curr_logic + 4 - prev_logic) & 0x03;

    // --- 异常检测与计数 ---

    if(diff == 2) 
    {
        // [异常1] 跨区突变
        MultiturnOpticalEncoder.MTAB.GlitchCnt++;
        MultiturnOpticalEncoder.MTAB.Check = ENC_STATUS_ERR_GLITCH; // 标记状态
        MultiturnOpticalEncoder.MTAB.Result = 0;
        
        // 注意：不 return，更新位置继续测，看后面还有没有错
        prev_logic = curr_logic; 
    }
    else if(diff != 1) 
    {
        // [异常2] 抖动/反转 (diff == 3)
        MultiturnOpticalEncoder.MTAB.JitterCnt++;
        MultiturnOpticalEncoder.MTAB.Check = ENC_STATUS_ERR_JITTER; // 标记状态
        MultiturnOpticalEncoder.MTAB.Result = 0;
        
        // 发生抖动时，不增加 change_cnt，但更新位置
        prev_logic = curr_logic;
    }
    else
    {
        // [正常] 正向旋转 (diff == 1)
        change_cnt++;
        prev_logic = curr_logic;
    }

    // 更新步数给上位机看
    MultiturnOpticalEncoder.MTAB.Cnt = change_cnt;

    // --- 结算逻辑 ---
    // 条件：回到起点 且 至少动了4步
    if((curr_logic == start_logic) && (change_cnt >= 4))
    {
        circle_done = 1; // 标记测试结束

        // 检查步数是否严格为4
        if(change_cnt != 4)
        {
            // [异常3] 步数异常
            MultiturnOpticalEncoder.MTAB.CountErrCnt++;
            MultiturnOpticalEncoder.MTAB.Check = ENC_STATUS_ERR_COUNT;
            MultiturnOpticalEncoder.MTAB.Result = 0;
        }

        // 最终综合判定
        // 只有：无突变、无抖动、且步数正好为4，才算 PASS
        if( (MultiturnOpticalEncoder.MTAB.GlitchCnt == 0) &&
            (MultiturnOpticalEncoder.MTAB.JitterCnt == 0) &&
            (MultiturnOpticalEncoder.MTAB.CountErrCnt == 0) ) // 这里的CntErrCnt等价于change_cnt==4判断
        {
            MultiturnOpticalEncoder.MTAB.Result = 1;
            MultiturnOpticalEncoder.MTAB.Check  = ENC_STATUS_PASS;
        }
        else
        {
            MultiturnOpticalEncoder.MTAB.Result = 0;
            // Check 保持最后一次检测到的错误状态
        }
    }
}


//==============================================================================
// 函数名称：MultiturnOpticalEncoderHallContinuousCheck
// 函数功能：HALL 连续采样检测
//==============================================================================
void MultiturnOpticalEncoderHallContinuousCheck(void)
{
    static uint8_t prev_logic  = 0xFF;
    static uint8_t start_logic = 0xFF;
    static uint8_t change_cnt  = 0;
    static uint8_t circle_done = 0;

    uint8_t curr_phys, curr_logic, diff;

    if(circle_done) return;

    curr_phys = PNH2612.HallSector;
    curr_logic = HALL_Map[curr_phys & 0x03];

    if(prev_logic == 0xFF)
    {
        prev_logic  = curr_logic;
        start_logic = curr_logic;
        change_cnt  = 0;
        circle_done = 0;

        MultiturnOpticalEncoder.Hall.Result      = 0;
        MultiturnOpticalEncoder.Hall.Check       = ENC_STATUS_TESTING;
        MultiturnOpticalEncoder.Hall.Cnt         = 0;
        MultiturnOpticalEncoder.Hall.GlitchCnt   = 0;
        MultiturnOpticalEncoder.Hall.JitterCnt   = 0;
        MultiturnOpticalEncoder.Hall.CountErrCnt = 0;
        return;
    }

    if(curr_logic == prev_logic) return;

    diff = (curr_logic + 4 - prev_logic) & 0x03;

    // --- 异常检测 ---

    if(diff == 2)
    {
        MultiturnOpticalEncoder.Hall.GlitchCnt++;
        MultiturnOpticalEncoder.Hall.Check = ENC_STATUS_ERR_GLITCH;
        MultiturnOpticalEncoder.Hall.Result = 0;
        prev_logic = curr_logic;
    }
    else if(diff != 1)
    {
        MultiturnOpticalEncoder.Hall.JitterCnt++;
        MultiturnOpticalEncoder.Hall.Check = ENC_STATUS_ERR_JITTER;
        MultiturnOpticalEncoder.Hall.Result = 0;
        prev_logic = curr_logic;
    }
    else
    {
        change_cnt++;
        prev_logic = curr_logic;
    }

    MultiturnOpticalEncoder.Hall.Cnt = change_cnt;

    // --- 结算 ---
    if((curr_logic == start_logic) && (change_cnt >= 4))
    {
        circle_done = 1;

        if(change_cnt != 4)
        {
            MultiturnOpticalEncoder.Hall.CountErrCnt++;
            MultiturnOpticalEncoder.Hall.Check = ENC_STATUS_ERR_COUNT;
            MultiturnOpticalEncoder.Hall.Result = 0;
        }

        if( (MultiturnOpticalEncoder.Hall.GlitchCnt == 0) &&
            (MultiturnOpticalEncoder.Hall.JitterCnt == 0) &&
            (MultiturnOpticalEncoder.Hall.CountErrCnt == 0) )
        {
            MultiturnOpticalEncoder.Hall.Result = 1;
            MultiturnOpticalEncoder.Hall.Check  = ENC_STATUS_PASS;
        }
        else
        {
            MultiturnOpticalEncoder.Hall.Result = 0;
        }
    }
}
//==============================================================================
// MultiturnOpticalEncoderTest
//==============================================================================
__ramfunc void MultiturnOpticalEncoderTest(volatile uint8_t TestItems)
{
  switch(TestItems){
  case MultiturnOpticalEncoderStopTest:
    
    break;
  case MultiturnOpticalEncoderMultiturnTest:
    MultiturnOpticalEncoderMultiturnReset();
    break;
  case MultiturnOpticalEncoderGetAllDataTest:
    MultiturnOpticalEncoderGetAllData();    
    break;
  case MultiturnOpticalEncoderReadAllEepromTest:
    MultiturnOpticalEncoderReadAllEeprom();
    break;
  case MultiturnOpticalEncoderInitializeTest://eeprom初始化
    MultiturnOpticalEncoderInitialize();
    break;    
  case MultiturnOpticalEncoderSpeedTest:
    //MultiturnOpticalEncoderSpeed();
    break;
  case MultiturnOpticalEncoderFirmwareVersionTest:
    //MultiturnOpticalEncoderFirmwareVersionRead();
    break;
  case MultiturnOpticalEncoderWriteAllEepromTest:
    //MultiturnOpticalEncoderWriteAllEeprom();
    break;
  case MultiturnOpticalEncoderAnalogDataTest://
    MultiturnOpticalEncoderTX(0x85, 0x00, 0x00, 0x00, 0x00); 
    break;
  case MultiturnOpticalEncoderWriteResultTest://写入测试结果
    MultiturnOpticalEncoderWriteResult();
    break;  
  case MultiturnOpticalEncoderTBTest://电池电压和温度测试
    MultiturnOpticalEncoderTB(); 
    break;
  case MultiturnOpticalEncoderOIPTest://打开内部协议开关
    MultiturnOpticalEncoderOpenInternalProtocol();    
    break;
  case MultiturnOpticalEncoderCIPTest://关闭内部协议开关
    MultiturnOpticalEncoderTX(0x6D, 0x00,Encoder_CIP_Test, 0x00, 0x00); 
    MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;      
    break;    
  case MultiturnOpticalEncoderWriteDateTest:
    MultiturnOpticalEncoderWriteDate();
    break; 
  case MultiturnOpticalEncoderDACTest:
    MultiturnOpticalEncoderDAC();
    break;
  case MultiturnOpticalEncoderLightIntensityTest:
    MultiturnOpticalEncoderLightIntensity();
    break;
  case MultiturnOpticalEncoderReadAnalogDataTest:
    MultiturnOpticalEncoderTX(0x85, 0x00, 0x00, 0x00, 0x00); 
    MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest; 
    break;
  case MultiturnOpticalEncoderReadInternalAlarmTest:
    MultiturnOpticalEncoderTX(0x75, 0x00, 0x00, 0x00, 0x00); 
    MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;     
    break;
  case MultiturnOpticalEncoderRMRNRSInitializeTest://RM_UP,RN_UP,RS_UP设置为90，RM_UP,RN_UP,RS_UP设置为0
    MultiturnOpticalEncoderWriteRMRNRS();
    MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;
    break;
  case MultiturnOpticalEncoderWriteHWRevTest:
    MultiturnOpticalEncoderWriteHWRev();
    break;
  case MultiturnOpticalEncoderSectorTest:
    MultiturnOpticalEncoderHallCheck();
    MultiturnOpticalEncoderMTABCheck();
    MotorEncoder.TestItem = MultiturnOpticalEncoderStopTest;
    break;
  case MultiturnOpticalEncoderMNSPositionTest:
    if(PNH2612.M.PositionFlag > 0){
      MultiturnOpticalEncoderTX(0x1A, 0x00, 0x00, 0x00, 0x00); 
      MultiturnOpticalEncoderMPositionMark1(); 
    }else{
      MultiturnOpticalEncoderTX(0x0D, 0x00, 0x00, 0x00, 0x00); 
      MultiturnOpticalEncoderMNSSpeedCheck();
      MultiturnOpticalEncoderMPositionMark();      
    }
    break;
  case MultiturnOpticalEncoderDACAdjustmentTest:
    MultiturnOpticalEncoderDACAdjustment();
    break;
  case MultiturnOpticalEncoderMNSAnalogMaxCheckTest:
    MultiturnOpticalEncoderMNSAnalogMaxCheck();
    break;
  }
}