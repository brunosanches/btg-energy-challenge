import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import re
import time
from functools import wraps
from datetime import datetime
from pathlib import Path


def read_data_file(file_path: str) -> pd.DataFrame:
    with open(file_path, 'r') as f:
        raw_file = f.readlines()

    list_dados = [line.split() for line in raw_file]
    float_raw_lines = [list(map(float, raw_line)) for raw_line in list_dados]
    return pd.DataFrame(float_raw_lines, columns=['lat', 'long', 'data_value'])


def read_contour_file(file_path: str) -> pd.DataFrame:
    line_split_comp = re.compile(r'\s*,')

    with open(file_path, 'r') as f:
        raw_file = f.readlines()

    l_raw_lines = [line_split_comp.split(raw_file_line.strip()) for raw_file_line in raw_file]
    l_raw_lines = list(filter(lambda item: bool(item[0]), l_raw_lines))
    float_raw_lines = [list(map(float, raw_line))[:2] for raw_line in l_raw_lines]
    header_line = float_raw_lines.pop(0)
    assert len(float_raw_lines) == int(header_line[0])
    return pd.DataFrame(float_raw_lines, columns=['lat', 'long'])

def is_point_in_contour(contour: np.ndarray, point: np.array) -> bool:
    # Using the raycast method, checks if point is inside de polygon defined by the contour
    # Some simplifications are made:
    # 1 - We draw a straight horizontal line, so every segment that don't intersect the y axis of the point is ignored
    # 2 - Segments left to the point are also ignored since the line begins at the point and goes to the right
    
    # Count the times that the ray intersects the polygon
    count = 0
    for i in range(len(contour)):
        # Get line from the contour
        pc1 = contour[i]
        pc2 = contour[(i+1) % len(contour)]

        # Simplification: We are drawning a straight horizontal line, so if point_y is not inside [pc1_y, pc2_y]
        # ignore this segment
        if point[1] < min(pc1[1], pc2[1]) or point[1] > max(pc1[1], pc2[1]):
            continue
        # The only segments that are interesting are the ones that are right to the point
        if point[0] > max(pc1[0], pc2[0]):
            continue
        # The remaining segment intersects our horizontal line just need to know where:
        # Check if the segment intersects another horizontal segment
        if np.isclose(point[1], pc1[1]) and np.isclose(point[1], pc2[1]):
            # If the precedent and the next points lies each on a different side of the ray, 
            # we consider that the ray intersected the line. As it will be counted by intersecting the
            # vertex (below) we add 1.
            precedent_point = contour[i-1]
            next_point = contour[(i+2) % len(contour)]
            if ((precedent_point[1] < point[1]) and (next_point[1] < [1])) or \
                ((precedent_point[1] > point[1]) and (next_point[1] > [1])):
                count += 1
            else:
                continue
        # Count intersection on the point only when it's the first point, to avoid counting double
        elif np.isclose(point[1], pc1[1]):
            count += 1
        elif np.isclose(point[1], pc2[1]):
            continue
        else:
            count += 1

    # If intersected an odd number of times, is inside the contour
    return count % 2 == 1

def apply_contour(contour_df: pd.DataFrame, data_df: pd.DataFrame) -> pd.DataFrame:
    # For each point, check if is inside contour and drop if not
    contour = np.array(contour_df)
    contour_mins = np.min(contour, axis=0)
    contour_maxes = np.max(contour, axis=0)

    # Filter points that aren't in the rectangle that covers the contour
    data_df = data_df.loc[
        np.logical_and.reduce([
            data_df['lat'] > contour_mins[0], 
            data_df['lat'] < contour_maxes[0], 
            data_df['long'] > contour_mins[1], 
            data_df['long'] < contour_maxes[1]
        ])
    ].copy()

    for index, row in data_df.iterrows():
        if not is_point_in_contour(contour, np.array([row['lat'], row['long']])):
            data_df.drop(index, inplace=True)

    return data_df

def create_plots(contour_df: pd.DataFrame, data_df: pd.DataFrame):
    pluviosity = data_df.groupby('date')[['data_value']].sum()\
        .rename(columns={'data_value': 'Pluviosity'})

    # Create plots with information per date
    n_dates = len(data_df['date'].unique())
    n_cols = int(np.sqrt(n_dates))
    n_rows = (n_dates + n_cols - 1) // n_cols

    fig, ax = plt.subplots(n_rows, n_cols, sharex=True, sharey=True, figsize=(10, 10))
    ax = ax.flatten()
    for i, date in enumerate(sorted(data_df['date'].unique())):
        # Plot contour
        ax[i].plot(contour_df['lat'], contour_df['long'])

        # Plot points inside it
        im = ax[i].scatter(x=data_df.loc[data_df['date'] == date, 'lat'], 
                    y=data_df.loc[data_df['date'] == date, 'long'], 
                    c=data_df.loc[data_df['date'] == date,'data_value'], 
                    cmap="Blues",
                    vmin=np.min(data_df['data_value']), 
                    vmax=np.max(data_df['data_value'])
                    )
        ax[i].set_title(date.strftime('%d-%m-%y'))
        
    fig.colorbar(im, ax=ax, orientation='vertical', fraction=0.02, pad=0.1, label='Precipitação')

    for j in range(n_dates, len(ax)):
        fig.delaxes(ax[j])
    # plt.show()
    fig.show()

    # Plots with aggregated information
    fig, ax = plt.subplots(ncols=2, figsize=(10, 5))
    ax[0].plot(pluviosity['Pluviosity'])
    ax[0].set_ylabel('Pluviosidade (mm)')
    ax[0].set_title('Pluviosidade por dia')
    for idx, row in pluviosity.iterrows():
        ax[0].annotate(f"{row['Pluviosity']:.1f}", (idx, row['Pluviosity']))

    ax[1].plot(pluviosity['Pluviosity'].cumsum())
    ax[1].set_ylabel('Pluviosidade acumulada (mm)')
    ax[1].set_title('Pluviosidade acumulada')
    for idx, row in pluviosity.cumsum().iterrows():
        ax[1].annotate(f"{row['Pluviosity']:.1f}", (idx, row['Pluviosity']))

    fig.autofmt_xdate(rotation=45)
    fig.show()
    plt.show()
    

def main() -> None:
    forecast_date = '011221'
    contour_df: pd.DataFrame = read_contour_file('PSATCMG_CAMARGOS.bln')

    forecast_files_path = Path('forecast_files/')

    # Join all datasets
    data_df = None
    for file in forecast_files_path.glob(f'ETA40_p{forecast_date}*.dat'):
        date = file.stem.split('p')[-1].split('a')[-1]

        if data_df is None:
            data_df = read_data_file(f'forecast_files/ETA40_p{forecast_date}a{date}.dat')
            data_df['date'] = datetime.strptime(date, "%d%m%y")
        else:
            tmp_df = read_data_file(f'forecast_files/ETA40_p{forecast_date}a{date}.dat')
            tmp_df['date'] = datetime.strptime(date, "%d%m%y")
            data_df = pd.concat([data_df, tmp_df], ignore_index=True)

    # Apply contour, removing points that aren't inside it 
    begin = time.time()
    data_df: pd.DataFrame = apply_contour(contour_df=contour_df, data_df=data_df)
    print(f'Elapsed time: {time.time() - begin}')

    # Calculate cumulated pluviosity
    pluviosity = data_df.groupby('date')[['data_value']].sum()\
        .rename(columns={'data_value': 'Pluviosity'})
    print("Cumulative Rainfall Forecast for the Camargos Hydroelectrict power plant for each day:")
    print(pluviosity)

    print(f"Cumulative Rainfall Forecast: {pluviosity['Pluviosity'].sum()} mm")

    # Plot
    create_plots(contour_df, data_df)

if __name__ == '__main__':
    main()
