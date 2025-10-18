#!/usr/bin/env python3
"""
Test script to verify TF-Luna LIDAR data flow.
"""

import serial
import time

def test_lidar(port='/dev/ttyS0', baudrate=115200):
    """Test LIDAR connection and display readings."""
    print(f"Opening {port} at {baudrate} baud...")
    
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=1,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS
        )
        
        print(f"✓ Port opened: {ser.name}")
        print(f"✓ Baudrate: {ser.baudrate}")
        print("\nWaiting for TF-Luna data (9-byte frames)...")
        print("Frame format: [0x59 0x59 Dist_L Dist_H Strength_L Strength_H Temp_L Temp_H Checksum]")
        print("-" * 80)
        
        frame_count = 0
        byte_buffer = []
        
        while frame_count < 20:  # Read 20 frames then stop
            # Read one byte
            byte = ser.read(1)
            
            if len(byte) == 0:
                print("⚠ Timeout - no data received")
                continue
            
            byte_val = byte[0]
            byte_buffer.append(byte_val)
            
            # TF-Luna frames start with 0x59 0x59
            if len(byte_buffer) >= 2 and byte_buffer[-2] == 0x59 and byte_buffer[-1] == 0x59:
                # Start of new frame, clear buffer
                byte_buffer = [0x59, 0x59]
            
            # When we have a complete 9-byte frame
            if len(byte_buffer) == 9:
                if byte_buffer[0] == 0x59 and byte_buffer[1] == 0x59:
                    # Parse the frame
                    distance = byte_buffer[2] + (byte_buffer[3] << 8)
                    strength = byte_buffer[4] + (byte_buffer[5] << 8)
                    temp_raw = byte_buffer[6] + (byte_buffer[7] << 8)
                    temperature = temp_raw / 8.0 - 256
                    checksum = byte_buffer[8]
                    
                    # Verify checksum
                    calc_checksum = sum(byte_buffer[:8]) & 0xFF
                    checksum_ok = "✓" if calc_checksum == checksum else "✗"
                    
                    frame_count += 1
                    print(f"Frame {frame_count:3d}: Distance={distance:4d}cm  "
                          f"Strength={strength:5d}  Temp={temperature:5.1f}°C  "
                          f"Checksum={checksum_ok}")
                    
                byte_buffer = []
        
        print("-" * 80)
        print(f"\n✓ Successfully read {frame_count} frames from LIDAR")
        ser.close()
        print("✓ Port closed")
        return True
        
    except serial.SerialException as e:
        print(f"✗ Serial error: {e}")
        return False
    except PermissionError:
        print(f"✗ Permission denied. Try: sudo usermod -a -G dialout $USER")
        print(f"  Then log out and back in.")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == "__main__":
    import sys
    
    port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyS0'
    
    print("=" * 80)
    print("TF-Luna LIDAR Test Script")
    print("=" * 80)
    
    success = test_lidar(port)
    
    if success:
        print("\n✓ LIDAR is working correctly!")
    else:
        print("\n✗ LIDAR test failed. Check:")
        print("  1. Wiring (TX→RX, RX→TX, power)")
        print("  2. Port permissions (dialout group)")
        print("  3. UART enabled in /boot/config.txt")
    
    sys.exit(0 if success else 1)
