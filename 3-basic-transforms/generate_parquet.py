import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import math

import polars as pl
from faker import Faker
from faker.providers import BaseProvider


@dataclass
class Measurement:
    id: int
    name: str
    age: float
    timestamp: datetime
    blood_pressure: float
    heart_rate: float
    temperature: float
    blood_glucose: float


class LifeStage(Enum):
    CUB = "CUB"
    JUV = "JUV"
    ADULT = "ADULT"
    SENIOR = "SENIOR"


fake = Faker()

name_pool = [
    "Icy Ingrid",
    "Peter Panda",
    "Arctic Archie",
    "Chilly Willy",
    "Cubby Coldpaws",
    "Blizzard Bob",
]

polar_bear_base_temp = dict(
    zip(
        name_pool,
        [
            37.5,
            40.0,
            37.5,
            37.5,
            37.5,
            37.5,
        ],
    )
)

polar_bear_base_weight = dict(
    zip(
        name_pool,
        [
            275,
            320,
            600,
            500,
            700,
            850,
        ],
    )
)
polar_bear_base_glucose = dict(
    zip(
        name_pool,
        [
            145,
            200,
            150,
            120,
            160,
            190,
        ],
    )
)

polar_bear_birth_day = dict(
    zip(
        name_pool,
        [
            datetime(year=2024 - age, month=month, day=day)
            for age, month, day in zip(
                (4, 2, 30, 10, 0, 40),
                (6, 3, 9, 11, 3, 8),
                (12, 10, 2, 19, 24, 28),
            )
        ],
    )
)
polar_bear_lifestage = {1: LifeStage.JUV, 4: LifeStage.ADULT, 15: LifeStage.SENIOR}


def temperature_per_day(timestamp: datetime, name: str) -> float:
    t = (
        timestamp - timestamp.replace(hour=0, minute=0, second=0)
    ).total_seconds() / 3600
    return polar_bear_base_temp[name] + 1.5 * math.sin(-math.pi / 12 * t - math.pi / 2)


def blood_glucose_per_day(timestamp: datetime, name: str) -> float:
    t = (
        timestamp - timestamp.replace(hour=0, minute=0, second=0)
    ).total_seconds() / 3600
    return polar_bear_base_glucose[name] + 5 * math.sin(-math.pi / 12 * t)


def weight_by_age(timestamp: datetime, name: str) -> float:
    t = (timestamp - polar_bear_birth_day[name]).total_seconds() / (3600 * 24 * 365)
    max_weight = polar_bear_base_weight[name]
    return max_weight / (1 + math.exp(-5 * t + 6))


class VetHealthCheck(Enum):
    HEALTHY = "HEALTHY"
    SICK = "SICK"
    INJURED = "INJURED"


@dataclass
class BatchMeasurement:
    name: str
    age: float
    vet: int
    years: int
    weight: float
    daily_steps: int
    timestamp: datetime
    vet_health_check: LifeStage
    life_stage: VetHealthCheck


dt = timedelta(days=365).total_seconds()


class MeasurementProvider(BaseProvider):
    __provider__ = "transaction"

    def measurement(self, name: str, timestamp: datetime) -> Measurement:
        timestamp += fake.time_delta(timedelta(minutes=10))
        age = (timestamp - polar_bear_birth_day[name]).total_seconds()
        heart_rate = 70 * math.exp(-1.5 * max(age, 0) / dt) + 70
        temperature = temperature_per_day(timestamp=timestamp, name=name)
        bg = blood_glucose_per_day(timestamp=timestamp, name=name)
        return Measurement(
            id=fake.uuid4(),
            name=name,
            age=age,
            timestamp=timestamp,
            blood_pressure=fake.random_int(60, 140),
            heart_rate=int(heart_rate + fake.random.gauss(0, 5)),
            temperature=round(temperature + fake.random.gauss(0, 0.25), 2),
            blood_glucose=int(bg + fake.random.gauss(0, 10)),
        )


vet_misspelling = {1: 0, 2: 10, 3: 0, 4: 20, 5: 50}


class BatchMeasurementProvider(BaseProvider):
    __provider__ = "batch_measurement"

    def batch_measurement(self, timestamp: datetime, name: str) -> BatchMeasurement:
        age = (timestamp - polar_bear_birth_day[name]).total_seconds()
        years = (timestamp - polar_bear_birth_day[name]).days // 365
        weight = weight_by_age(timestamp=timestamp, name=name)
        variation = int(min(10, weight / 10))
        life_stage = LifeStage.CUB
        for age_limit, stage in polar_bear_lifestage.items():
            if age_limit <= years:
                life_stage = stage
            if age_limit > years:
                break
        vet = fake.random_int(1, 5)

        return BatchMeasurement(
            name=(
                name.upper()
                if fake.boolean(chance_of_getting_true=vet_misspelling[vet])
                else name
            ),
            age=age,
            years=years,
            weight=weight + fake.random.gauss(0, variation),
            daily_steps=fake.random_int(1000, 20000),
            timestamp=timestamp,
            vet=vet,
            vet_health_check=(
                VetHealthCheck.SICK
                if name == "Peter Panda"  # Peter Panda is always sick
                else fake.random_element(VetHealthCheck)
            ),
            life_stage=life_stage,
        )


if __name__ == "__main__":
    fake.add_provider(MeasurementProvider)
    fake.add_provider(BatchMeasurementProvider)

    days = 365 * 4
    N = int(days * 24)
    N_batch = int(days // 2)
    timestamps = [datetime(2020, 4, 20) + i * timedelta(hours=1) for i in range(N)]
    measurements = [
        fake.measurement(name, timestamp)
        for timestamp in timestamps
        for name in name_pool
    ]
    records = []
    with open("data/measurements.csv", "w") as f:
        for t in measurements:
            if t.age < 0:
                continue
            records.append(
                (
                    t.name,
                    t.timestamp,
                    t.blood_pressure,
                    t.heart_rate,
                    t.temperature,
                    t.blood_glucose,
                )
            )
            f.write(
                f"{t.id}|{t.name}|{t.timestamp}|{t.blood_pressure}|{t.heart_rate}|{t.temperature}|{t.blood_glucose}\n"
            )
    print(
        pl.from_records(
            records,
            schema=[
                "name",
                "timestamp",
                "blood_pressure",
                "heart_rate",
                "temperature",
                "blood_glucose",
            ],
        )
        .select(pl.all().shrink_dtype())
        .write_parquet("data/measurements.parquet")
    )

    timestamps = [
        datetime(2020, 4, 20, 6, 15) + i * timedelta(days=2) for i in range(N_batch)
    ]
    batch_measurements = [
        fake.batch_measurement(timestamp, name)
        for timestamp in timestamps
        for name in name_pool
    ]
    records = []
    with open("data/batch_measurements.csv", "w") as f:
        for t in batch_measurements:
            if t.age < 0:
                continue
            records.append(
                (
                    t.name,
                    t.vet,
                    t.years,
                    t.weight,
                    t.daily_steps,
                    t.timestamp,
                    t.vet_health_check.value,
                    t.life_stage.value,
                )
            )
            ts = datetime.strftime(t.timestamp, r"%d%m%YT%H:%M:%S")
            f.write(
                f"{t.name}|{t.years}|{t.weight}|{t.daily_steps}|{ts}|{t.vet_health_check.value}|{t.life_stage.value}\n"
            )
    print(
        pl.from_records(
            records,
            schema=[
                "name",
                "vet",
                "age",
                "weight",
                "daily_steps",
                "timestamp",
                "vet_health_check",
                "life_stage",
            ],
        )
        .select(pl.all().shrink_dtype())
        .write_parquet("data/batch_measurements.parquet")
    )