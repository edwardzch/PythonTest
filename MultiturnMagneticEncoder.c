#include "gpio_config.h"
#include "pit_config.h"
#include "uart_config.h"
#include "MultiturnMagneticEncoder.h"
#include "Function.h"
#include "ModBus.h"
//==============================================================================
// DEFINES
//==============================================================================


strMULMGTEnc   MultiturnMagneticEncoder = {0};
extern volatile uint8_t  Work_Alarm;
extern uart_transfer_t uart0_transfer;
void MultiturnMagneticEncoderHallCheck(void);
//==============================================================================
// MultiturnMagneticEncoderTXOneByte
//==============================================================================
void MultiturnMagneticEncoderTXOneByte(volatile uint8_t Idle)
{
  MultiturnMagneticEncoder.TimeoutCnt ++;
  MultiturnMagneticEncoder.TxData[0] = Idle;                                         
  uart0_transfer.data = (uint8_t *)&MultiturnMagneticEncoder.TxData[0];
  uart0_transfer.dataSize = 1;           
  Encoder485DE();                                                         
  for (volatile uint8_t i=0; i<5; i++);
  UART_SendDMA0(&uart0_transfer);   
}
//==============================================================================
// MultiturnMagneticEncoderRX
//==============================================================================
void MultiturnMagneticEncoderRX(void)
{
    //static uint8_t   i = 0;
    MultiturnMagneticEncoder.RxData[MultiturnMagneticEncoder.RxDataCnt++] = UART0->D;                                                  //Recieve request to auto clear flag     
    
    if(MultiturnMagneticEncoder.RxDataCnt >= 1){
      switch(MultiturnMagneticEncoder.RxData[0]){
      case 0x1A:
        if(MultiturnMagneticEncoder.RxDataCnt == 11){
          UART_EnableRx(UART0, false);
          MultiturnMagneticEncoder.TimeoutCnt = 0;  
          MultiturnMagneticEncoder.RxDataCnt = 0;      
          MultiturnMagneticEncoder.RxID = MultiturnMagneticEncoder.RxData[0];
          MultiturnMagneticEncoder.Status.all = MultiturnMagneticEncoder.RxData[1];
          MultiturnMagneticEncoder.SingleTurnPosition = ((MultiturnMagneticEncoder.RxData[4] << 16) | (MultiturnMagneticEncoder.RxData[3] << 8) | MultiturnMagneticEncoder.RxData[2]) & 0xFFFFFFFF;
          MotorEncoder.SingleTurnPosition = MultiturnMagneticEncoder.SingleTurnPosition;
          MultiturnMagneticEncoder.ResolutionID = MultiturnMagneticEncoder.RxData[5];
          MotorEncoder.ResolutionID = MultiturnMagneticEncoder.ResolutionID;
          MultiturnMagneticEncoder.MultiTurnPosition = ((MultiturnMagneticEncoder.RxData[7] << 8) | MultiturnMagneticEncoder.RxData[6]) & 0xFFFF;
          MotorEncoder.MultiTurnPosition = MultiturnMagneticEncoder.MultiTurnPosition;
          MultiturnMagneticEncoder.Error.all = MultiturnMagneticEncoder.RxData[9];
          MultiturnMagneticEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.RxData, 10); 
          if(MultiturnMagneticEncoder.XorCrcData != MultiturnMagneticEncoder.RxData[10]){
            MultiturnMagneticEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnMagneticEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }
          if(Motor.Flag.bit.ReadyTest){
            Motor_SpeedTest(MultiturnMagneticEncoder.ResolutionID, MultiturnMagneticEncoder.SingleTurnPosition);
          }          
        }
        break;      
      case 0x02:
        if(MultiturnMagneticEncoder.RxDataCnt == 6){
          UART_EnableRx(UART0, false);
          MultiturnMagneticEncoder.TimeoutCnt = 0;  
          MultiturnMagneticEncoder.RxDataCnt = 0;     
          MultiturnMagneticEncoder.RxID = MultiturnMagneticEncoder.RxData[0];
          MultiturnMagneticEncoder.Status.all = MultiturnMagneticEncoder.RxData[1];
          MultiturnMagneticEncoder.SingleTurnPosition = ((MultiturnMagneticEncoder.RxData[4] << 16) | (MultiturnMagneticEncoder.RxData[3] << 8) | MultiturnMagneticEncoder.RxData[2]) & 0xFFFFFFFF;
          MotorEncoder.SingleTurnPosition = MultiturnMagneticEncoder.SingleTurnPosition;
          MultiturnMagneticEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.RxData, 5);
          if(MultiturnMagneticEncoder.XorCrcData != MultiturnMagneticEncoder.RxData[5]){
            MultiturnMagneticEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnMagneticEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }
        }
        break;      
      case 0x62:
        if(MultiturnMagneticEncoder.RxDataCnt == 6){
          UART_EnableRx(UART0, false);
          MultiturnMagneticEncoder.TimeoutCnt = 0;  
          MultiturnMagneticEncoder.RxDataCnt = 0;     
          MultiturnMagneticEncoder.RxID = MultiturnMagneticEncoder.RxData[0];
          MultiturnMagneticEncoder.Status.all = MultiturnMagneticEncoder.RxData[1];
          MultiturnMagneticEncoder.SingleTurnPosition = ((MultiturnMagneticEncoder.RxData[4] << 16) | (MultiturnMagneticEncoder.RxData[3] << 8) | MultiturnMagneticEncoder.RxData[2]) & 0xFFFFFFFF;
          MultiturnMagneticEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.RxData, 5);
          if(MultiturnMagneticEncoder.XorCrcData != MultiturnMagneticEncoder.RxData[5]){
            MultiturnMagneticEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnMagneticEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }
        }
        break;        
      case 0xEA:
        if(MultiturnMagneticEncoder.RxDataCnt==4){
          UART_EnableRx(UART0, false);
          MultiturnMagneticEncoder.TimeoutCnt = 0;  
          MultiturnMagneticEncoder.RxDataCnt = 0; 
          MultiturnMagneticEncoder.RxID = MultiturnMagneticEncoder.RxData[0];
          MultiturnMagneticEncoder.Eeprom.ReturnAddress = MultiturnMagneticEncoder.RxData[1] & 0x7F;
          if(MultiturnMagneticEncoder.Eeprom.ReturnAddress == MultiturnMagneticEncoderPNSAddress){
            MultiturnMagneticEncoder.Eeprom.ReturnPage = MultiturnMagneticEncoder.RxData[2];
            MultiturnMagneticEncoder.Eeprom.Status.bit.Busy = (MultiturnMagneticEncoder.RxData[1] >> 7) & 0xFF;
            MultiturnMagneticEncoder.Eeprom.DataBuffer[MultiturnMagneticEncoder.Eeprom.ReturnPage][MultiturnMagneticEncoder.Eeprom.ReturnAddress] = MultiturnMagneticEncoder.RxData[2];   
          }else if(MultiturnMagneticEncoder.Eeprom.ReturnAddress < MultiturnMagneticEncoderPNSAddress){
            MultiturnMagneticEncoder.Eeprom.Status.bit.Busy = (MultiturnMagneticEncoder.RxData[1] >> 7) & 0xFF;
            MultiturnMagneticEncoder.Eeprom.DataBuffer[MultiturnMagneticEncoder.Eeprom.ReturnPage][MultiturnMagneticEncoder.Eeprom.ReturnAddress] = MultiturnMagneticEncoder.RxData[2];            
          }   
          MultiturnMagneticEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.RxData, 3);
          if(MultiturnMagneticEncoder.XorCrcData != MultiturnMagneticEncoder.RxData[3]){
            MultiturnMagneticEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnMagneticEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }
        }  
        break;
      case 0x32:
        if(MultiturnMagneticEncoder.RxDataCnt==4){
          UART_EnableRx(UART0, false);
          MultiturnMagneticEncoder.TimeoutCnt = 0;  
          MultiturnMagneticEncoder.RxDataCnt = 0; 
          MultiturnMagneticEncoder.RxID = MultiturnMagneticEncoder.RxData[0];
          MultiturnMagneticEncoder.Eeprom.ReturnAddress = MultiturnMagneticEncoder.RxData[1] & 0x7F;
          if(MultiturnMagneticEncoder.Eeprom.ReturnAddress == MultiturnMagneticEncoderPNSAddress){
            MultiturnMagneticEncoder.Eeprom.ReturnPage = MultiturnMagneticEncoder.RxData[2];
            MultiturnMagneticEncoder.Eeprom.Status.bit.Busy = (MultiturnMagneticEncoder.RxData[1] >> 7) & 0xFF;
            MultiturnMagneticEncoder.Eeprom.DataBuffer[MultiturnMagneticEncoder.Eeprom.ReturnPage][MultiturnMagneticEncoder.Eeprom.ReturnAddress] = MultiturnMagneticEncoder.RxData[2];            
          }else if(MultiturnMagneticEncoder.Eeprom.ReturnAddress < MultiturnMagneticEncoderPNSAddress){
            MultiturnMagneticEncoder.Eeprom.Status.bit.Busy = (MultiturnMagneticEncoder.RxData[1] >> 7) & 0xFF;
            MultiturnMagneticEncoder.Eeprom.DataBuffer[MultiturnMagneticEncoder.Eeprom.ReturnPage][MultiturnMagneticEncoder.Eeprom.ReturnAddress] = MultiturnMagneticEncoder.RxData[2];            
          }
          MultiturnMagneticEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.RxData, 3);
          if(MultiturnMagneticEncoder.XorCrcData != MultiturnMagneticEncoder.RxData[3]){
            MultiturnMagneticEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnMagneticEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }
        }          
        break;
      case 0x85:
        if(MultiturnMagneticEncoder.RxDataCnt == 12){
          UART_EnableRx(UART0, false);
          MultiturnMagneticEncoder.TimeoutCnt = 0;  
          MultiturnMagneticEncoder.RxDataCnt = 0; 
          MultiturnMagneticEncoder.RxID = MultiturnMagneticEncoder.RxData[0];           
          MultiturnMagneticEncoder.Hall.Sector = (MultiturnMagneticEncoder.RxData[10] & 0x30) >> 4;
          MultiturnMagneticEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.RxData, 11);
          if(MultiturnMagneticEncoder.XorCrcData != MultiturnMagneticEncoder.RxData[11]){
            MultiturnMagneticEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnMagneticEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }
        }
        break;  
      case 0x25:
        if(MultiturnMagneticEncoder.RxDataCnt==10){
          UART_EnableRx(UART0, false);
          MultiturnMagneticEncoder.TimeoutCnt = 0; 
          MultiturnMagneticEncoder.RxDataCnt = 0; 
          MultiturnMagneticEncoder.RxID = MultiturnMagneticEncoder.RxData[0];
          MultiturnMagneticEncoder.SingleTurnPosition = ((MultiturnMagneticEncoder.RxData[3] << 16) | (MultiturnMagneticEncoder.RxData[2] << 8) | MultiturnMagneticEncoder.RxData[1]) & 0xFFFFFFFF;
          MotorEncoder.SingleTurnPosition = MultiturnMagneticEncoder.SingleTurnPosition >> 6;         
          MultiturnMagneticEncoder.Hall.Sector = (MultiturnMagneticEncoder.RxData[5] & 0x30) >> 4;
          MultiturnMagneticEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.RxData, 9);
          if(MultiturnMagneticEncoder.XorCrcData != MultiturnMagneticEncoder.RxData[9]){
            MultiturnMagneticEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnMagneticEncoder.XorCrcError;
            Work_Alarm = 0x02;
          } 
          if(Motor.Flag.bit.ReadyTest){
            Motor_SpeedTest(MultiturnMagneticEncoder.ResolutionID, MotorEncoder.SingleTurnPosition);
            MultiturnMagneticEncoderHallCheck();
          }          
        }     
        break;          
      case 0xAD:
        if(MultiturnMagneticEncoder.RxDataCnt==(MultiturnMagneticEncoder.Eeprom.SetDNum + 5)){
          UART_EnableRx(UART0, false);
          MultiturnMagneticEncoder.TimeoutCnt = 0;
          MultiturnMagneticEncoder.RxDataCnt = 0; 
          MultiturnMagneticEncoder.RxID = MultiturnMagneticEncoder.RxData[0];
          MultiturnMagneticEncoder.Eeprom.ReturnPage = MultiturnMagneticEncoder.RxData[1];
          MultiturnMagneticEncoder.Eeprom.ReturnAddress = MultiturnMagneticEncoder.RxData[2];
          MultiturnMagneticEncoder.Eeprom.ReturnDNum = MultiturnMagneticEncoder.RxData[3];
          MultiturnMagneticEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.RxData, (MultiturnMagneticEncoder.Eeprom.ReturnDNum + 4));
          if(MultiturnMagneticEncoder.XorCrcData != MultiturnMagneticEncoder.RxData[(MultiturnMagneticEncoder.Eeprom.ReturnDNum + 4)]){
            MultiturnMagneticEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnMagneticEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }else{ 
            for(volatile uint16_t j=0; j<MultiturnMagneticEncoder.Eeprom.ReturnDNum; j++){
              MultiturnMagneticEncoder.Eeprom.DataBuffer[MultiturnMagneticEncoder.Eeprom.ReturnPage][MultiturnMagneticEncoder.Eeprom.ReturnAddress + j] = MultiturnMagneticEncoder.RxData[4 + j];
            }
          }
        }          
        break;
      case 0x35:
        if(MultiturnMagneticEncoder.RxDataCnt==(MultiturnMagneticEncoder.Eeprom.SetDNum + 5)){
          UART_EnableRx(UART0, false);
          MultiturnMagneticEncoder.TimeoutCnt = 0;
          MultiturnMagneticEncoder.RxDataCnt = 0; 
          MultiturnMagneticEncoder.RxID = MultiturnMagneticEncoder.RxData[0];
          MultiturnMagneticEncoder.Eeprom.ReturnPage = MultiturnMagneticEncoder.RxData[1];
          MultiturnMagneticEncoder.Eeprom.ReturnAddress = MultiturnMagneticEncoder.RxData[2];
          MultiturnMagneticEncoder.Eeprom.ReturnDNum = MultiturnMagneticEncoder.RxData[3];      
          MultiturnMagneticEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.RxData, (MultiturnMagneticEncoder.Eeprom.ReturnDNum + 4));
          if(MultiturnMagneticEncoder.XorCrcData != MultiturnMagneticEncoder.RxData[(MultiturnMagneticEncoder.Eeprom.ReturnDNum + 4)]){
            MultiturnMagneticEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnMagneticEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }else{ 
            for(volatile uint16_t j=0; j<MultiturnMagneticEncoder.Eeprom.ReturnDNum; j++){
              MultiturnMagneticEncoder.Eeprom.DataBuffer[MultiturnMagneticEncoder.Eeprom.ReturnPage][MultiturnMagneticEncoder.Eeprom.ReturnAddress + j] = MultiturnMagneticEncoder.RxData[4 + j];
            }
          }
        }        
        break;  
      case 0x3D://读led光强度值、温度值、电池电压
        if(MultiturnMagneticEncoder.RxDataCnt==6){
          UART_EnableRx(UART0, false);
          MultiturnMagneticEncoder.TimeoutCnt = 0;   
          MultiturnMagneticEncoder.RxDataCnt = 0; 
          MultiturnMagneticEncoder.RxID = MultiturnMagneticEncoder.RxData[0];
          MultiturnMagneticEncoder.Temperature = MultiturnMagneticEncoder.RxData[3];
          MultiturnMagneticEncoder.BatteryVoltage = MultiturnMagneticEncoder.RxData[4];
          MultiturnMagneticEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.RxData, 5);
          if(MultiturnMagneticEncoder.XorCrcData != MultiturnMagneticEncoder.RxData[5]){
            MultiturnMagneticEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnMagneticEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }
        }          
        break; 
      case 0x75:
        if(MultiturnMagneticEncoder.RxDataCnt==5){
          UART_EnableRx(UART0, false);
          MultiturnMagneticEncoder.TimeoutCnt = 0;    
          MultiturnMagneticEncoder.RxDataCnt = 0;
          MultiturnMagneticEncoder.RxID = MultiturnMagneticEncoder.RxData[0];
          MultiturnMagneticEncoder.InternalAlarm1 = MultiturnMagneticEncoder.RxData[1];
          MultiturnMagneticEncoder.InternalAlarm2 = MultiturnMagneticEncoder.RxData[2];
          MultiturnMagneticEncoder.InternalAlarm3 = MultiturnMagneticEncoder.RxData[3];
          MultiturnMagneticEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.RxData, 4);
          if(MultiturnMagneticEncoder.XorCrcData != MultiturnMagneticEncoder.RxData[4]){
            MultiturnMagneticEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnMagneticEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }
        }           
        break;        
      case 0x40:
        if(MultiturnMagneticEncoder.RxDataCnt>=3){
          switch(MultiturnMagneticEncoder.RxData[1]){
          case 0x45:
            if(MultiturnMagneticEncoder.RxDataCnt==4){
              UART_EnableRx(UART0, false);
              MultiturnMagneticEncoder.TimeoutCnt = 0;
              MultiturnMagneticEncoder.RxDataCnt = 0;  
              MultiturnMagneticEncoder.ResolutionID = MultiturnMagneticEncoder.RxData[2];
              MultiturnMagneticEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.RxData, 3);
              if(MultiturnMagneticEncoder.XorCrcData != MultiturnMagneticEncoder.RxData[3]){
                MultiturnMagneticEncoder.XorCrcError = 1;
                ModBus.Error.bit.EC = MultiturnMagneticEncoder.XorCrcError;
                Work_Alarm = 0x02;
              }               
            }
            break;
          case 0x46:
            if(MultiturnMagneticEncoder.RxDataCnt==3){
              UART_EnableRx(UART0, false);
              MultiturnMagneticEncoder.TimeoutCnt = 0;
              MultiturnMagneticEncoder.RxDataCnt = 0;               
              if(MultiturnMagneticEncoder.RxData[2] != 0xF0){
                MultiturnMagneticEncoder.XorCrcError = 1;
                ModBus.Error.bit.EC = MultiturnMagneticEncoder.XorCrcError;
                Work_Alarm = 0x02;
              }               
            }
            break;
          case 0x51:
            if(MultiturnMagneticEncoder.RxDataCnt==6){
              UART_EnableRx(UART0, false);
              MultiturnMagneticEncoder.TimeoutCnt = 0;
              MultiturnMagneticEncoder.RxDataCnt = 0;               
              MultiturnMagneticEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.RxData, 5);
              if(MultiturnMagneticEncoder.XorCrcData != MultiturnMagneticEncoder.RxData[5]){
                MultiturnMagneticEncoder.XorCrcError = 1;
                ModBus.Error.bit.EC = MultiturnMagneticEncoder.XorCrcError;
                Work_Alarm = 0x02;
              }               
            }
            break;  
          case 0x52:
            if(MultiturnMagneticEncoder.RxDataCnt==6){
              UART_EnableRx(UART0, false);
              MultiturnMagneticEncoder.TimeoutCnt = 0;
              MultiturnMagneticEncoder.RxDataCnt = 0;               
              MultiturnMagneticEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.RxData, 5);
              if(MultiturnMagneticEncoder.XorCrcData != MultiturnMagneticEncoder.RxData[5]){
                MultiturnMagneticEncoder.XorCrcError = 1;
                ModBus.Error.bit.EC = MultiturnMagneticEncoder.XorCrcError;
                Work_Alarm = 0x02;
              } 
              if(MultiturnMagneticEncoder.RxData[2] == 0x11){
                MT6835Addr.Reg0x11 = MultiturnMagneticEncoder.RxData[4];
                if(MT6835Addr.Reg0x11 == MT6835Addr.Reg0x11_True){
                  MT6835Addr.RegBit.bit.Bit11 = 1;
                }
              }else if(MultiturnMagneticEncoder.RxData[2] == 0xDA){
                MT6835Addr.Reg0xDA = MultiturnMagneticEncoder.RxData[4];
                if(MT6835Addr.Reg0xDA == MT6835Addr.Reg0xDA_True){
                  MT6835Addr.RegBit.bit.BitDA = 1;
                }
              }else if(MultiturnMagneticEncoder.RxData[2] == 0xEA){
                MT6835Addr.Reg0xEA = MultiturnMagneticEncoder.RxData[4];
                if(MT6835Addr.Reg0xEA == MT6835Addr.Reg0xEA_True){
                  MT6835Addr.RegBit.bit.BitEA = 1;
                }                
              }else if(MultiturnMagneticEncoder.RxData[2] == 0xEC){
                MT6835Addr.Reg0xEC = MultiturnMagneticEncoder.RxData[4];
                if(MT6835Addr.Reg0xEC == MT6835Addr.Reg0xEC_True){
                  MT6835Addr.RegBit.bit.BitEC = 1;
                }                
              }else if(MultiturnMagneticEncoder.RxData[2] == 0x12){
                MT6835Addr.Reg0x12 = MultiturnMagneticEncoder.RxData[4];
                if(MT6835Addr.Reg0x12 == MT6835Addr.Reg0x12_True){
                  MT6835Addr.RegBit.bit.Bit12 = 1;
                }                
              }
            }
            break;            
          }
        }
        break;
      case 0x6D:
        if(MultiturnMagneticEncoder.RxDataCnt==6){
          UART_EnableRx(UART0, false);
          MultiturnMagneticEncoder.TimeoutCnt = 0;
          MultiturnMagneticEncoder.RxDataCnt = 0; 
          MultiturnMagneticEncoder.RxID = MultiturnMagneticEncoder.RxData[0];
          switch(MultiturnMagneticEncoder.IPID){
          case Encoder_ced_Test:
            MultiturnMagneticEncoder.Status0x6D = MultiturnMagneticEncoder.RxData[4];//STATUS：0 清除失败 STATUS：1 清除成功 STATUS：2 清除无效，已清除一次，不能再清除 STATUS：4 指令无效            
            break;
          case Encoder_OIP_Test:
            MultiturnMagneticEncoder.OIPStatus = MultiturnMagneticEncoder.RxData[4];
            if(MultiturnMagneticEncoder.Cnt.CFOIP == 5){
              MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;      
              MultiturnMagneticEncoder.Cnt.CFOIP = 0;
              if(MultiturnMagneticEncoder.OIPStatus == 0){
                Work_Alarm = 0x07;
              }           
            }
            if(MultiturnMagneticEncoder.OIPStatus == 4){
               Work_Alarm = 0x08;
            }            
            break;
          case Encoder_CIP_Test:
            
            break;            
          }
          MultiturnMagneticEncoder.XorCrcData = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.RxData, 5);
          if(MultiturnMagneticEncoder.XorCrcData != MultiturnMagneticEncoder.RxData[5]){
            MultiturnMagneticEncoder.XorCrcError = 1;
            ModBus.Error.bit.EC = MultiturnMagneticEncoder.XorCrcError;
            Work_Alarm = 0x02;
          }                   
        }            
        break;          
      default:
          MultiturnMagneticEncoder.RxDataCnt = 0; 
          break;              
      }
    }  
}
//==============================================================================
// MultiturnMagneticEncoderTX
//==============================================================================
void MultiturnMagneticEncoderTX(volatile uint8_t Idle, uint16_t Addr, uint8_t Data)
{
  static uint8_t j = 0;
  switch(Idle){
  case 0x62:
    MultiturnMagneticEncoderTXOneByte(Idle);   
    break;
  case 0x1A:
    MultiturnMagneticEncoderTXOneByte(Idle);         
    break;
  case 0x02:
    MultiturnMagneticEncoderTXOneByte(Idle);           
    break;    
  case 0xEA:
    MultiturnMagneticEncoder.TimeoutCnt ++;
    MultiturnMagneticEncoder.TxData[0] = Idle;                                                //CF                 
    MultiturnMagneticEncoder.TxData[1] = Addr; 
    MultiturnMagneticEncoder.TxData[2] = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.TxData, 2); 
    uart0_transfer.data = (uint8_t *)&MultiturnMagneticEncoder.TxData[0];
    uart0_transfer.dataSize = 3;           
    Encoder485DE();                                                          //Write enabled
    for (volatile uint8_t i=0; i<5; i++);
    UART_SendDMA0(&uart0_transfer);         
    break;
  case 0x32:
    MultiturnMagneticEncoder.TimeoutCnt ++;
    MultiturnMagneticEncoder.TxData[0] = Idle;                                                //CF                 
    MultiturnMagneticEncoder.TxData[1] = Addr; 
    MultiturnMagneticEncoder.TxData[2] = Data; 
    MultiturnMagneticEncoder.TxData[3] = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.TxData, 3); 
    uart0_transfer.data = (uint8_t *)&MultiturnMagneticEncoder.TxData[0];
    uart0_transfer.dataSize = 4;           
    Encoder485DE();                                                          //Write enabled
    for (volatile uint8_t i=0; i<5; i++);
    UART_SendDMA0(&uart0_transfer);    
    break;
  case 0x85:
    MultiturnMagneticEncoderTXOneByte(Idle);   
    break; 
  case 0x75://读取内部报警
    MultiturnMagneticEncoderTXOneByte(Idle);   
    break;     
  case 0x25://读取当前位置值及Hall逻辑电平值、MTAB逻辑电平
    MultiturnMagneticEncoderTXOneByte(Idle);  
    break;    
  case 0xAD:
    MultiturnMagneticEncoder.TimeoutCnt ++;
    MultiturnMagneticEncoder.TxData[0] = Idle;                                                //CF                 
    MultiturnMagneticEncoder.TxData[1] = MultiturnMagneticEncoder.Eeprom.SetPage; 
    MultiturnMagneticEncoder.TxData[2] = MultiturnMagneticEncoder.Eeprom.SetAddress; 
    MultiturnMagneticEncoder.TxData[3] = MultiturnMagneticEncoder.Eeprom.SetDNum;
    MultiturnMagneticEncoder.TxData[4] = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.TxData, 4); 
    uart0_transfer.data = (uint8_t *)&MultiturnMagneticEncoder.TxData[0];
    uart0_transfer.dataSize = 5;           
    Encoder485DE();                                                          //Write enabled
    for (volatile uint8_t i=0; i<5; i++);
    UART_SendDMA0(&uart0_transfer);       
    break;
  case 0x35:
    MultiturnMagneticEncoder.TimeoutCnt ++;
    MultiturnMagneticEncoder.TxData[0] = Idle;                                                //CF                 
    MultiturnMagneticEncoder.TxData[1] = MultiturnMagneticEncoder.Eeprom.SetPage; 
    MultiturnMagneticEncoder.TxData[2] = MultiturnMagneticEncoder.Eeprom.SetAddress; 
    MultiturnMagneticEncoder.TxData[3] = MultiturnMagneticEncoder.Eeprom.SetDNum;
    for(j=0; j<MultiturnMagneticEncoder.Eeprom.SetDNum; j++){
      MultiturnMagneticEncoder.TxData[4+j] = MultiturnMagneticEncoder.Eeprom.DataBuffer[MultiturnMagneticEncoder.Eeprom.SetPage][MultiturnMagneticEncoder.Eeprom.SetAddress+j];
    }
    MultiturnMagneticEncoder.TxData[4+j] = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.TxData, (4+j));     
    uart0_transfer.data = (uint8_t *)&MultiturnMagneticEncoder.TxData[0];
    uart0_transfer.dataSize = (5+j);           
    Encoder485DE();                                                          //Write enabled
    for (volatile uint8_t i=0; i<5; i++);
    UART_SendDMA0(&uart0_transfer);  
    break;  
  case 0x3D://电池电压和温度读取
    MultiturnMagneticEncoderTXOneByte(Idle);    
    break;    
  case 0x6D://eeprom初始化结果读取
    MultiturnMagneticEncoder.TimeoutCnt ++;
    if(Data == Encoder_ced_Test){
      MultiturnMagneticEncoder.IPID = Data;
      MultiturnMagneticEncoder.TxData[0] = Idle;                                                //CF                 
      MultiturnMagneticEncoder.TxData[1] = 0x63; //'c'
      MultiturnMagneticEncoder.TxData[2] = 0x65; //'e'
      MultiturnMagneticEncoder.TxData[3] = 0x64; //'d'      
    }else if(Data == Encoder_CIP_Test){
      MultiturnMagneticEncoder.IPID = Data;
      MultiturnMagneticEncoder.TxData[0] = Idle;                                                //CF                 
      MultiturnMagneticEncoder.TxData[1] = 0x43; //'C'
      MultiturnMagneticEncoder.TxData[2] = 0x49; //'I'
      MultiturnMagneticEncoder.TxData[3] = 0x50; //'P'            
    }else if(Data == Encoder_OIP_Test){
      MultiturnMagneticEncoder.IPID = Data;
      MultiturnMagneticEncoder.TxData[0] = Idle;                                                //CF                 
      MultiturnMagneticEncoder.TxData[1] = 0x4F; //'O'
      MultiturnMagneticEncoder.TxData[2] = 0x49; //'I'
      MultiturnMagneticEncoder.TxData[3] = 0x50; //'P'         
    }
    MultiturnMagneticEncoder.TxData[4] = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.TxData, 4); 
    uart0_transfer.data = (uint8_t *)&MultiturnMagneticEncoder.TxData[0];
    uart0_transfer.dataSize = 5;           
    Encoder485DE();                                                          //Write enabled
    for (volatile uint8_t i=0; i<5; i++);
    UART_SendDMA0(&uart0_transfer); 
    break; 
  case 0x40:
    MultiturnMagneticEncoder.TimeoutCnt ++;
    MultiturnMagneticEncoder.TxData[0] = Idle;                                                //CF  
    MultiturnMagneticEncoder.TxData[1] = (uint8_t)(Addr & 0xFF); 
    if(MultiturnMagneticEncoder.TxData[1] == 0x46){
      MultiturnMagneticEncoder.TxData[2] = Data;
      MultiturnMagneticEncoder.TxData[3] = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.TxData, 3); 
      uart0_transfer.data = (uint8_t *)&MultiturnMagneticEncoder.TxData[0];
      uart0_transfer.dataSize = 4;       
    }else{
      MultiturnMagneticEncoder.TxData[2] = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.TxData, 2); 
      uart0_transfer.data = (uint8_t *)&MultiturnMagneticEncoder.TxData[0];
      uart0_transfer.dataSize = 3;         
    }            
    Encoder485DE();                                                          //Write enabled
    for (volatile uint8_t i=0; i<5; i++);
    UART_SendDMA0(&uart0_transfer);     
    break;    
  }
  if(MultiturnMagneticEncoder.TimeoutCnt > 5){
    ModBus.Error.bit.DC = 1;
    Work_Alarm = 0x01;
  }     
}

void EncoderTXRegister(volatile uint8_t Idle, uint8_t Status, uint8_t Addr, uint8_t Data)
{
  if(Status == 0x51){
    MultiturnMagneticEncoder.TimeoutCnt ++;
    MultiturnMagneticEncoder.TxData[0] = Idle;                                                //CF                 
    MultiturnMagneticEncoder.TxData[1] = Status; 
    MultiturnMagneticEncoder.TxData[2] = Addr;
    MultiturnMagneticEncoder.TxData[3] = 0x00;
    MultiturnMagneticEncoder.TxData[4] = Data; 
    MultiturnMagneticEncoder.TxData[5] = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.TxData, 5); 
    uart0_transfer.data = (uint8_t *)&MultiturnMagneticEncoder.TxData[0];
    uart0_transfer.dataSize = 6;     
  }else if(Status == 0x52){
    MultiturnMagneticEncoder.TimeoutCnt ++;
    MultiturnMagneticEncoder.TxData[0] = Idle;                                                //CF                 
    MultiturnMagneticEncoder.TxData[1] = Status; 
    MultiturnMagneticEncoder.TxData[2] = Addr;
    MultiturnMagneticEncoder.TxData[3] = 0x00;
    MultiturnMagneticEncoder.TxData[4] = CRC8_Check((uint8_t *)MultiturnMagneticEncoder.TxData, 4); 
    uart0_transfer.data = (uint8_t *)&MultiturnMagneticEncoder.TxData[0];
    uart0_transfer.dataSize = 5;        
  }          
  Encoder485DE();                                                          //Write enabled
  for (volatile uint8_t i=0; i<5; i++);
  UART_SendDMA0(&uart0_transfer); 
  if(MultiturnMagneticEncoder.TimeoutCnt > 5){
    ModBus.Error.bit.DC = 1;
    Work_Alarm = 0x01;
  }    
}
//==============================================================================
// MultiturnMagneticEncoderMultiturnReset
//==============================================================================
void MultiturnMagneticEncoderMultiturnReset(void)
{
  if(MultiturnMagneticEncoder.Cnt.CF62 < 100){
    MultiturnMagneticEncoderTX(0x62, 0x00, 0x00);
    MultiturnMagneticEncoder.Cnt.CF62 ++;
    if(MultiturnMagneticEncoder.Cnt.CF62 == 100){
      MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
    }
  }
}

////==============================================================================
//// MultiturnMagneticEncoderFirmwareVersionRead
////==============================================================================
//void MultiturnMagneticEncoderFirmwareVersionRead(void)
//{
//  MultiturnMagneticEncoder.Eeprom.SetPage = 0x03;
//  MultiturnMagneticEncoder.Eeprom.SetDNum = 0x04;
//  MultiturnMagneticEncoder.Eeprom.SetAddress = 0x14;
//  MultiturnMagneticEncoderTX(0xAD, 0x00, 0x00); 
//  MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
//}
//==============================================================================
// MultiturnMagneticEncoderReadHWRev
//==============================================================================
void MultiturnMagneticEncoderReadHWRev(void)
{
  MotorEncoder.HWRev[0] = MultiturnMagneticEncoder.Eeprom.DataBuffer[2][0x70];
  MotorEncoder.HWRev[1] = '.';
  MotorEncoder.HWRev[2] = MultiturnMagneticEncoder.Eeprom.DataBuffer[2][0x71];
  MotorEncoder.HWRev[3] = '.';
  MotorEncoder.HWRev[4] = MultiturnMagneticEncoder.Eeprom.DataBuffer[2][0x72] + 0x30;
  MotorEncoder.HWRev[5] = '.';
  MotorEncoder.HWRev[6] = MultiturnMagneticEncoder.Eeprom.DataBuffer[2][0x73] + 0x30;
  hexToAsciiString(MotorEncoder.HWRev, MotorEncoder.HWRevBuffer, 7);
  //MotorEncoder.HWRev[7] = '\0';
}
//==============================================================================
// MultiturnMagneticEncoderReadFWRev
//==============================================================================
void MultiturnMagneticEncoderReadFWRev(void)
{
  MotorEncoder.FWRev[0] = MultiturnMagneticEncoder.Eeprom.DataBuffer[3][20] + 0x30;
  MotorEncoder.FWRev[1] = '.';
  MotorEncoder.FWRev[2] = MultiturnMagneticEncoder.Eeprom.DataBuffer[3][21] + 0x30;
  MotorEncoder.FWRev[3] = '.';
  MotorEncoder.FWRev[4] = MultiturnMagneticEncoder.Eeprom.DataBuffer[3][22] + 0x30;
  MotorEncoder.FWRev[5] = '.';
  MotorEncoder.FWRev[6] = MultiturnMagneticEncoder.Eeprom.DataBuffer[3][23];
  hexToAsciiString(MotorEncoder.FWRev, MotorEncoder.FWRevBuffer, 7);
  //MotorEncoder.FWRev[7] = '\0';
}

//==============================================================================
// MultiturnMagneticEncoderHallCCWCheck
// FCT PCBA器件朝上
//==============================================================================
void MultiturnMagneticEncoderHallCCWCheck(void)
{
    switch(MultiturnMagneticEncoder.Hall.Buffer[0]){
    case 0x00:
      if(MultiturnMagneticEncoder.Hall.Buffer[1] == 1 && MultiturnMagneticEncoder.Hall.Buffer[2] == 2 && MultiturnMagneticEncoder.Hall.Buffer[3] == 3 && MotorEncoder.PitCnt >= 485 && MotorEncoder.PitCnt <= 800){
        MultiturnMagneticEncoder.Hall.Result = 1;
        MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
      }else{
        MultiturnMagneticEncoder.Hall.Result = 0;
      }
      break;
    case 0x01:
      if(MultiturnMagneticEncoder.Hall.Buffer[1] == 2 && MultiturnMagneticEncoder.Hall.Buffer[2] == 3 && MultiturnMagneticEncoder.Hall.Buffer[3] == 0 && MotorEncoder.PitCnt >= 485 && MotorEncoder.PitCnt <= 800){
        MultiturnMagneticEncoder.Hall.Result = 1;
        MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
      }else{
        MultiturnMagneticEncoder.Hall.Result = 0;
      }        
      break;
    case 0x02:
      if(MultiturnMagneticEncoder.Hall.Buffer[1] == 3 && MultiturnMagneticEncoder.Hall.Buffer[2] == 0 && MultiturnMagneticEncoder.Hall.Buffer[3] == 1 && MotorEncoder.PitCnt >= 485 && MotorEncoder.PitCnt <= 800){
        MultiturnMagneticEncoder.Hall.Result = 1;
        MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
      }else{
        MultiturnMagneticEncoder.Hall.Result = 0;
      }        
      break;
    case 0x03:
      if(MultiturnMagneticEncoder.Hall.Buffer[1] == 0 && MultiturnMagneticEncoder.Hall.Buffer[2] == 1 && MultiturnMagneticEncoder.Hall.Buffer[3] == 2 && MotorEncoder.PitCnt >= 485 && MotorEncoder.PitCnt <= 800){//通过循环压力测试分析，有一部分MotorEncoder.PitCnt会小于500，在485到500之间
        MultiturnMagneticEncoder.Hall.Result = 1;
        MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
      }else{
        MultiturnMagneticEncoder.Hall.Result = 0;
      }        
      break;
    } 
}
//==============================================================================
// MultiturnMagneticEncoderHallCWCheck
// FCT PCBA器件朝下
//==============================================================================
void MultiturnMagneticEncoderHallCWCheck(void)
{
    switch(MultiturnMagneticEncoder.Hall.Buffer[0]){
    case 0x00:
      if(MultiturnMagneticEncoder.Hall.Buffer[1] == 3 && MultiturnMagneticEncoder.Hall.Buffer[2] == 2 && MultiturnMagneticEncoder.Hall.Buffer[3] == 1 && MotorEncoder.PitCnt >= 485 && MotorEncoder.PitCnt <= 800){
        MultiturnMagneticEncoder.Hall.Result = 1;
        MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
      }else{
        MultiturnMagneticEncoder.Hall.Result = 0;
      }
      break;
    case 0x01:
      if(MultiturnMagneticEncoder.Hall.Buffer[1] == 0 && MultiturnMagneticEncoder.Hall.Buffer[2] == 3 && MultiturnMagneticEncoder.Hall.Buffer[3] == 2 && MotorEncoder.PitCnt >= 485 && MotorEncoder.PitCnt <= 800){
        MultiturnMagneticEncoder.Hall.Result = 1;
        MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
      }else{
        MultiturnMagneticEncoder.Hall.Result = 0;
      }        
      break;
    case 0x02:
      if(MultiturnMagneticEncoder.Hall.Buffer[1] == 1 && MultiturnMagneticEncoder.Hall.Buffer[2] == 0 && MultiturnMagneticEncoder.Hall.Buffer[3] == 3 && MotorEncoder.PitCnt >= 485 && MotorEncoder.PitCnt <= 800){
        MultiturnMagneticEncoder.Hall.Result = 1;
        MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
      }else{
        MultiturnMagneticEncoder.Hall.Result = 0;
      }        
      break;
    case 0x03:
      if(MultiturnMagneticEncoder.Hall.Buffer[1] == 2 && MultiturnMagneticEncoder.Hall.Buffer[2] == 1 && MultiturnMagneticEncoder.Hall.Buffer[3] == 0 && MotorEncoder.PitCnt >= 485 && MotorEncoder.PitCnt <= 800){//通过循环压力测试分析，有一部分MotorEncoder.PitCnt会小于500，在485到500之间
        MultiturnMagneticEncoder.Hall.Result = 1;
        MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
      }else{
        MultiturnMagneticEncoder.Hall.Result = 0;
      }        
      break;
    } 
}
//==============================================================================
// MultiturnMagneticEncoderHallCheck
//==============================================================================
void MultiturnMagneticEncoderHallCheck(void)
{

  if(MultiturnMagneticEncoder.Hall.Check){
    if(MultiturnMagneticEncoder.Eeprom.DataBuffer[3][20] == 2){
      MultiturnMagneticEncoderHallCCWCheck();
    }else if(MultiturnMagneticEncoder.Eeprom.DataBuffer[3][20] == 3){
      MultiturnMagneticEncoderHallCWCheck();
    }
  }else{
    MotorEncoder.PitCnt ++;
    if(MultiturnMagneticEncoder.Hall.Cnt > 0){
      if(MultiturnMagneticEncoder.Hall.Sector != MultiturnMagneticEncoder.Hall.Buffer[MultiturnMagneticEncoder.Hall.Cnt-1]){
        MultiturnMagneticEncoder.Hall.Buffer[MultiturnMagneticEncoder.Hall.Cnt] = MultiturnMagneticEncoder.Hall.Sector;
        MultiturnMagneticEncoder.Hall.Cnt ++;           
        if(MultiturnMagneticEncoder.Hall.Cnt == 4){
          MultiturnMagneticEncoder.Hall.Check = 1;
        }
      }  
    }else{
      MultiturnMagneticEncoder.Hall.Buffer[MultiturnMagneticEncoder.Hall.Cnt] = MultiturnMagneticEncoder.Hall.Sector;
      MultiturnMagneticEncoder.Hall.Cnt ++;      
    }    
  }  
}
//==============================================================================
// MultiturnMagneticEncoderHallRead
//==============================================================================
void MultiturnMagneticEncoderHallRead(void)
{
  MultiturnMagneticEncoderTX(0x25, 0x00, 0x00); 
  if(MultiturnMagneticEncoder.Cnt.CF25 < 100){
    MultiturnMagneticEncoder.Cnt.CF25 ++;
  }else{
    Motor.Flag.bit.ReadyTest = 1;
  }
}

//==============================================================================
// MultiturnMagneticEncoderReadAllEeprom
//==============================================================================
void MultiturnMagneticEncoderReadAllEeprom(void)
{
  if(MultiturnMagneticEncoder.Eeprom.SetPage < MultiturnMagneticEncoderPageNumber){  //1ms 一个周期，4页 4ms读完
    MultiturnMagneticEncoder.Eeprom.SetDNum = 0x80;
    MultiturnMagneticEncoder.Eeprom.SetAddress = 0x00;
    MultiturnMagneticEncoderTX(0xAD, 0x00, 0x00);         
    MultiturnMagneticEncoder.Eeprom.SetPage ++;  
  }else{
    MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
    MultiturnMagneticEncoderReadHWRev();
    MultiturnMagneticEncoderReadFWRev();
    MultiturnMagneticEncoder.ReadResolutionID = MultiturnMagneticEncoder.Eeprom.DataBuffer[2][0x65];
    
  }
}

//==============================================================================
// MultiturnMagneticEncoderWriteResult
//==============================================================================
void MultiturnMagneticEncoderWriteResult(void)
{
  MultiturnMagneticEncoder.Eeprom.SetPage = 0x02;
  MultiturnMagneticEncoder.Eeprom.SetAddress = 0x00;
  MultiturnMagneticEncoder.Eeprom.SetDNum = 0x01;
  MultiturnMagneticEncoder.Eeprom.DataBuffer[MultiturnMagneticEncoder.Eeprom.SetPage][MultiturnMagneticEncoder.Eeprom.SetAddress] = 0x09; //9代表整机测试和PCBA测试完成，1代表PCBA测试完成，由于我们是整机和PCBA测试结合一起了，所以写入9
  MultiturnMagneticEncoderTX(0x35, 0x00, 0x00); 
  MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
}

////==============================================================================
//// MultiturnMagneticEncoderWriteAllEeprom
////==============================================================================
//void MultiturnMagneticEncoderWriteAllEeprom(void)
//{
//  if(MultiturnMagneticEncoder.Eeprom.Page < MultiturnMagneticEncoderPageNumber){
//    MultiturnMagneticEncoder.Eeprom.DNum = 0x80;
//    MultiturnMagneticEncoder.Eeprom.Address = 0x00;
//    MultiturnMagneticEncoderTX(0x35, 0x00, 0x00);
//    MultiturnMagneticEncoder.Eeprom.Page ++;
//  }
//}
//==============================================================================
// MultiturnMagneticEncoderInitialize
//==============================================================================
void MultiturnMagneticEncoderInitialize(void)
{
  if(MultiturnMagneticEncoder.Cnt.CFced < 5){
    MultiturnMagneticEncoderTX(0x6D, 0x00,Encoder_ced_Test); 
    MultiturnMagneticEncoder.Cnt.CFced ++;
  }else{
    MultiturnMagneticEncoder.Cnt.CFced = 0;
    MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;    
  }
}
//==============================================================================
// MultiturnMagneticEncoderSpeed
//==============================================================================
void MultiturnMagneticEncoderSpeed(void)
{
  MultiturnMagneticEncoderTX(0x1A, 0x00, 0x00);
  if(MultiturnMagneticEncoder.Cnt.CF1A < 100){
    MultiturnMagneticEncoder.Cnt.CF1A ++;
  }else{
    Motor.Flag.bit.ReadyTest = 1;
  }
}
//==============================================================================
// MultiturnMagneticEncoderGetAllData
//==============================================================================
void MultiturnMagneticEncoderGetAllData(void)
{
  static uint8_t i = 0;
  if(i == 0){
    MultiturnMagneticEncoderTX(0x1A, 0x00, 0x00);
    i = 1;
  }else{    
    MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
    MultiturnMagneticEncoderTX(0x75, 0x00, 0x00);
    i = 0;
  }  
}
//==============================================================================
// MultiturnMagneticEncoderTB
//==============================================================================
void MultiturnMagneticEncoderTB(void)
{
  MultiturnMagneticEncoderTX(0x3D, 0x00, 0x00);
  MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;  
}
//==============================================================================
// MultiturnMagneticEncoderOpenInternalProtocol
//==============================================================================
void MultiturnMagneticEncoderOpenInternalProtocol(void)
{
  if(MultiturnMagneticEncoder.Cnt.CFOIP < 5){
    MultiturnMagneticEncoderTX(0x6D, 0x00,Encoder_OIP_Test); 
    MultiturnMagneticEncoder.Cnt.CFOIP ++;
  }else{
    MultiturnMagneticEncoder.Cnt.CFOIP = 0;
    MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;  
  }
}
//==============================================================================
// MultiturnMagneticEncoderWriteDate
//==============================================================================
void MultiturnMagneticEncoderWriteDate(void)
{
  MultiturnMagneticEncoder.Eeprom.SetPage = 0x02;
  MultiturnMagneticEncoder.Eeprom.SetAddress = 0x68;
  MultiturnMagneticEncoder.Eeprom.SetDNum = 0x04;
  MultiturnMagneticEncoder.Eeprom.DataBuffer[MultiturnMagneticEncoder.Eeprom.SetPage][MultiturnMagneticEncoder.Eeprom.SetAddress] = MotorEncoder.TestYear;
  MultiturnMagneticEncoder.Eeprom.DataBuffer[MultiturnMagneticEncoder.Eeprom.SetPage][MultiturnMagneticEncoder.Eeprom.SetAddress+1] = MotorEncoder.TestMoon;
  MultiturnMagneticEncoder.Eeprom.DataBuffer[MultiturnMagneticEncoder.Eeprom.SetPage][MultiturnMagneticEncoder.Eeprom.SetAddress+2] = MotorEncoder.TestDay;
  MultiturnMagneticEncoder.Eeprom.DataBuffer[MultiturnMagneticEncoder.Eeprom.SetPage][MultiturnMagneticEncoder.Eeprom.SetAddress+3] = MotorEncoder.TestHour;
  MultiturnMagneticEncoderTX(0x35, 0x00, 0x00); 
  MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
}
//==============================================================================
// MultiturnMagneticEncoderSetResolution
//==============================================================================
void MultiturnMagneticEncoderSetResolution(void)
{
  MultiturnMagneticEncoderTX(0x40, 0x46,MotorEncoder.SetResolutionID);
  MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
}
//==============================================================================
// MgtMagneticEncoderReadResolution
//==============================================================================
void MultiturnMagneticEncoderReadResolution(void)
{
  MultiturnMagneticEncoderTX(0x40, 0x45,0x00);
  MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
}
//==============================================================================
// MultiturnMagneticEncoderWriteHWRevTest
//==============================================================================
void MultiturnMagneticEncoderWriteHWRev(void)
{
  MultiturnMagneticEncoder.Eeprom.SetPage = 0x02;
  MultiturnMagneticEncoder.Eeprom.SetAddress = 0x70;
  MultiturnMagneticEncoder.Eeprom.SetDNum = 0x04;
  MultiturnMagneticEncoder.Eeprom.DataBuffer[MultiturnMagneticEncoder.Eeprom.SetPage][MultiturnMagneticEncoder.Eeprom.SetAddress] = 'H';
  MultiturnMagneticEncoder.Eeprom.DataBuffer[MultiturnMagneticEncoder.Eeprom.SetPage][MultiturnMagneticEncoder.Eeprom.SetAddress+1] = 'M';
  MultiturnMagneticEncoder.Eeprom.DataBuffer[MultiturnMagneticEncoder.Eeprom.SetPage][MultiturnMagneticEncoder.Eeprom.SetAddress+2] = 1;
  MultiturnMagneticEncoder.Eeprom.DataBuffer[MultiturnMagneticEncoder.Eeprom.SetPage][MultiturnMagneticEncoder.Eeprom.SetAddress+3] = MotorEncoder.HWRevData;
  MultiturnMagneticEncoderTX(0x35, 0x00, 0x00); 
  MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;
}
//==============================================================================
// MultiturnMagneticEncoderWriteRegister
//==============================================================================
void MultiturnMagneticEncoderWriteRegister(void)
{
  static uint8_t i = 0;
  
  switch(i){
  case 0:
    MT6835Addr.Reg0x11_True = 0x06;
    EncoderTXRegister(0x40,0x51,0x11,MT6835Addr.Reg0x11_True);
    i = 1;
    break;
  case 1:
    MT6835Addr.Reg0xDA_True = 0x01;
    EncoderTXRegister(0x40,0x51,0xDA,MT6835Addr.Reg0xDA_True);
    i = 2;    
    break;
  case 2:
    MT6835Addr.Reg0xEA_True = 0x01;
    EncoderTXRegister(0x40,0x51,0xEA,MT6835Addr.Reg0xEA_True);
    i = 3;     
    break;
  case 3:
    MT6835Addr.Reg0xEC_True = 0x02;
    EncoderTXRegister(0x40,0x51,0xEC,MT6835Addr.Reg0xEC_True);
    i = 4;     
    break;
  case 4:
    MT6835Addr.Reg0x12_True = 0xA0;
    EncoderTXRegister(0x40,0x51,0x12,MT6835Addr.Reg0x12_True);
    MotorEncoder.TestItem = MultiturnMagneticEncoderReadRegisterTest;
    i = 0;     
    break;    
  } 
}
//==============================================================================
// MultiturnMagneticEncoderReadRegister
//==============================================================================
void MultiturnMagneticEncoderReadRegister(void)
{
  static uint8_t i = 0;
  
  switch(i){
  case 0:
    EncoderTXRegister(0x40,0x52,0x11,0x06);
    i = 1;
    break;
  case 1:
    EncoderTXRegister(0x40,0x52,0xDA,0x01);
    i = 2;    
    break;
  case 2:
    EncoderTXRegister(0x40,0x52,0xEA,0x01);
    i = 3;     
    break;
  case 3:
    EncoderTXRegister(0x40,0x52,0xEC,0x02);
    i = 4;     
    break;
  case 4:
    EncoderTXRegister(0x40,0x52,0x12,0xA0);
    i = 5;     
    break; 
  case 5:
    if(MT6835Addr.RegBit.all == 0x1F){
      MT6835Addr.TestRegData = 1;
    }else{
      MT6835Addr.TestRegData = 2;
    }
    MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;    
    break;
  } 
}
//==============================================================================
// MultiturnMagneticEncoderTest
//==============================================================================
__ramfunc void MultiturnMagneticEncoderTest(volatile uint8_t TestItems)
{
  switch(TestItems){
  case MultiturnMagneticEncoderStopTest:
    
    break;
  case MultiturnMagneticEncoderMultiturnTest:
    MultiturnMagneticEncoderMultiturnReset();
    break;
  case MultiturnMagneticEncoderGetAllDataTest:
    MultiturnMagneticEncoderGetAllData();    
    break;
  case MultiturnMagneticEncoderReadAllEepromTest:
    MultiturnMagneticEncoderReadAllEeprom();
    break;
  case MultiturnMagneticEncoderInitializeTest://eeprom初始化
    MultiturnMagneticEncoderInitialize();
    break;    
  case MultiturnMagneticEncoderSpeedTest:
    //MultiturnMagneticEncoderSpeed();
    break;
  case MultiturnMagneticEncoderFirmwareVersionTest:
    //MultiturnMagneticEncoderFirmwareVersionRead();
    break;
  case MultiturnMagneticEncoderWriteAllEepromTest:
    //MultiturnMagneticEncoderWriteAllEeprom();
    break;
  case MultiturnMagneticEncoderHallTest://
    MultiturnMagneticEncoderHallRead();
    break;
  case MultiturnMagneticEncoderWriteResultTest://写入测试结果
    MultiturnMagneticEncoderWriteResult();
    break;  
  case MultiturnMagneticEncoderTBTest://电池电压和温度测试
    MultiturnMagneticEncoderTB(); 
    break;
  case MultiturnMagneticEncoderOIPTest://打开内部协议开关
    MultiturnMagneticEncoderOpenInternalProtocol();    
    break;
  case MultiturnMagneticEncoderCIPTest://关闭内部协议开关
    MultiturnMagneticEncoderTX(0x6D, 0x00,Encoder_CIP_Test); 
    MotorEncoder.TestItem = MultiturnMagneticEncoderStopTest;      
    break;    
  case MultiturnMagneticEncoderWriteDateTest:
    MultiturnMagneticEncoderWriteDate();
    break;   
  case MultiturnMagneticEncoderSetResolutionTest:
    MultiturnMagneticEncoderSetResolution();
    break;
  case MultiturnMagneticEncoderReadResolutionTest:
    MultiturnMagneticEncoderReadResolution();
    break;
  case MultiturnMagneticEncoderWriteHWRevTest:
    MultiturnMagneticEncoderWriteHWRev();
    break; 
  case MultiturnMagneticEncoderWriteRegisterTest:
    MultiturnMagneticEncoderWriteRegister();
    break; 
  case MultiturnMagneticEncoderReadRegisterTest:
    MultiturnMagneticEncoderReadRegister();
    break;         
  }
}