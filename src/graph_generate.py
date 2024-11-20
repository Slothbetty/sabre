import pandas as pd
import matplotlib.pyplot as plt
import argparse

def generate_graph(abrarray):
    # 字典来存储每个 ABR 的 DataFrame
    dataframes = {}

    # 颜色列表
    colors = ['blue', 'orange', 'green', 'red', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan']
    marker = 'o'  # 使用相同的标记符号

    # 加载每个 CSV 文件的数据并存储到字典中
    for abr in abrarray:
        dataframes[abr] = pd.read_csv(f'{abr}.csv')

    # 绘制所有 ABR 算法的 network_bandwidth vs time，使用对数刻度
    plt.figure(figsize=(10, 5))
    for i, abr in enumerate(abrarray):
        plt.plot(
            dataframes[abr]['time'], 
            dataframes[abr]['network_bandwidth'], 
            label=f'{abr} Network Bandwidth', 
            color=colors[i % len(colors)], 
            marker=marker,  # 使用相同的标记符号
            alpha=0.8  # 设置透明度
        )
    plt.xlabel('Time(ms)')
    plt.ylabel('Network Bandwidth(kbps)')
    plt.yscale('log')  # 设置 y 轴为对数刻度
    plt.title("Network Bandwidth vs Time for All ABR Algorithms (Log Scale)")
    plt.legend()
    plt.grid(visible=True, which='both', linestyle='--', alpha=0.5)
    plt.show()

    # 绘制所有 ABR 算法的 bitrate vs time，使用对数刻度
    plt.figure(figsize=(10, 5))
    for i, abr in enumerate(abrarray):
        plt.plot(
            dataframes[abr]['time'], 
            dataframes[abr]['bitrate'], 
            label=f'{abr} Bitrate', 
            color=colors[i % len(colors)], 
            marker=marker,  # 使用相同的标记符号
            alpha=0.8  # 设置透明度
        )
    plt.xlabel('Time(ms)')
    plt.ylabel('Bitrate(kbps)')
    plt.yscale('log')  # 设置 y 轴为对数刻度
    plt.title("Bitrate vs Time for All ABR Algorithms (Log Scale)")
    plt.legend()
    plt.grid(visible=True, which='both', linestyle='--', alpha=0.5)
    plt.show()

    # 绘制所有 ABR 算法的 buffer_level vs time，使用对数刻度
    plt.figure(figsize=(10, 5))
    for i, abr in enumerate(abrarray):
        plt.plot(
            dataframes[abr]['time'], 
            dataframes[abr]['buffer_level'], 
            label=f'{abr} Buffer Level', 
            color=colors[i % len(colors)], 
            marker=marker,  # 使用相同的标记符号
            alpha=0.8  # 设置透明度
        )
    plt.xlabel('Time(ms)')
    plt.ylabel('Buffer Level(ms)')
    plt.yscale('log')  # 设置 y 轴为对数刻度
    plt.title("Buffer Level vs Time for All ABR Algorithms (Log Scale)")
    plt.legend()
    plt.grid(visible=True, which='both', linestyle='--', alpha=0.5)
    plt.show()

    # 绘制所有 ABR 算法的 rebuffer_time vs time，使用对数刻度
    plt.figure(figsize=(10, 5))
    for i, abr in enumerate(abrarray):
        plt.plot(
            dataframes[abr]['time'], 
            dataframes[abr]['rebuffer_time'], 
            label=f'{abr} Rebuffer Time', 
            color=colors[i % len(colors)], 
            marker=marker,  # 使用相同的标记符号
            alpha=0.8  # 设置透明度
        )
    plt.xlabel('Time(ms)')
    plt.ylabel('Rebuffer Time(ms)')
    plt.yscale('log')  # 设置 y 轴为对数刻度
    plt.title("Rebuffer Time vs Time for All ABR Algorithms (Log Scale)")
    plt.legend()
    plt.grid(visible=True, which='both', linestyle='--', alpha=0.5)
    plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate graphs for specified ABR algorithms')
    parser.add_argument('-a', '--abr', type=str, nargs='+', required=True, help='Array of ABR algorithms to use (space-separated)')
    args = parser.parse_args()

    # 将 ABR 算法数组传递给 generate_graph 函数
    generate_graph(args.abr)
