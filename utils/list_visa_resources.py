import pyvisa

def list_resources():
    rm = pyvisa.ResourceManager()
    try:
        resources = rm.list_resources()
        print("Available VISA Resources:")
        for res in resources:
            print(f"  - {res}")
            try:
                # 尝试获取一些 ID 信息
                # 注意：打开资源可能会干扰其他正在运行的程序，所以这里只列出，不打开
                pass 
            except:
                pass
        
        if not resources:
            print("  No VISA resources found.")
            
    except Exception as e:
        print(f"Error listing resources: {e}")

if __name__ == "__main__":
    list_resources()
