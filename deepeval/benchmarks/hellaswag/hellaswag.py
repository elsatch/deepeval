from typing import List
from datasets import load_dataset
from tqdm import tqdm  
from deepeval.dataset import Golden
from deepeval.benchmarks.base_benchmark import DeepEvalBaseBenchmark
from deepeval.models import DeepEvalBaseLLM
from deepeval.benchmarks.hellaswag.task import HellaSwagTask
from deepeval.benchmarks.hellaswag.template import HellaSwagTemplate
from deepeval.scorer import Scorer
import pandas as pd 

# TODO: to be deleted
from deepeval.models import GPTModel


class HellaSwag(DeepEvalBaseBenchmark):

    def __init__(self, tasks: List[HellaSwagTask] = None, n_shots: int=10):
        assert n_shots <= 15, "HellaSwag only supports n_shots <= 15."
        super().__init__()
        self.tasks: List[HellaSwagTask] = list(HellaSwagTask) if tasks is None else tasks
        self.scorer = Scorer()
        self.dataset: Dataset = None
        self.shots_dataset: List[dict] = None
        self.n_shots = n_shots
        self.predictions: Optional[pd.DataFrame] = None
        self.task_scores: Optional[pd.DataFrame] = None
        self.score: Optional[float] = None

    def evaluate(self, model: DeepEvalBaseLLM) -> dict:
        overall_correct_predictions = 0
        overall_total_predictions = 0
        predictions_row = [] 
        scores_row = [] 

        for task in self.tasks:
            goldens = self.load_benchmark_dataset(task)
            task_correct_predictions = 0
            task_total_predictions = len(goldens)
            overall_total_predictions += len(goldens)

            # Calculate task accuracy
            for golden in tqdm(goldens, desc=f'Processing {task.value}'):
                prediction, score = self.predict(model, task, golden).values()
                if score:
                    task_correct_predictions += 1
                    overall_correct_predictions += 1
                predictions_row.append((task.value, golden.input, prediction, score))
            task_accuracy = task_correct_predictions / task_total_predictions
            print(f"MMLU Task Accuracy (task={task.value}): {task_accuracy}")
            scores_row.append((task.value, task_accuracy))

        # Calculate overall accuracy
        overall_accuracy = overall_correct_predictions / overall_total_predictions
        print(f"Overall MMLU Accuracy: {overall_accuracy}")

        # Create a DataFrame from task_results_data
        # Columns: 'Task', 'Input', 'Prediction', 'Score'
        self.predictions = pd.DataFrame(predictions_row, columns=['Task', 'Input', 'Prediction', 'Correct'])
        self.task_scores = pd.DataFrame(scores_row, columns=['Task', 'Accuracy'])
        self.score = overall_accuracy

        return overall_accuracy
    

    def predict(self, model: DeepEvalBaseLLM, task: HellaSwagTask, golden: Golden) -> dict:
        # Define prompt template
        assert self.shots_dataset != None, "Example dataset is empty. Call load_benchmark."
        prompt: dict = HellaSwagTemplate.generate_output(
            train_set=self.shots_dataset, input=golden.input, task=task, n_shots=self.n_shots
        )
        prediction = model.generate(prompt)[0]
    
        # Define Metric
        score = self.scorer.exact_match_score(golden.expected_output, prediction)
        return {'prediction': prediction, 'score': score}


    def load_benchmark_dataset(self, task: HellaSwagTask) -> List[Golden]:
        # If dataset has been previously loaded, load from 
        # instance var (to save time)
        if self.dataset:
            dataset = self.dataset
        else:
            dataset = load_dataset("Rowan/hellaswag", trust_remote_code=True)
            self.dataset = dataset

        # If dataset has not been previously loaded, construct 
        # dataset of examples and save as instance var (to save time)
        if not self.shots_dataset:
            train_set = dataset['train']
            shots_set = []
            categories_seen = set()
            for data in train_set:
                category = data['activity_label']
                if category not in categories_seen:
                    categories_seen.add(category)
                    shots_set.append(data)
            self.shots_dataset = shots_set
            
        # Construct test set (using validation here because HellaSwag 
        # does not provide outputs for test set in HF dataset)
        val_set = dataset["validation"].filter(lambda data: data['activity_label'] == task.value)
        choices =  ['A', 'B', 'C', 'D']
        goldens: List[Golden] = []
        for data in val_set:
            input = HellaSwagTemplate.format_question(data, include_answer=False)
            golden = Golden(input=input, expectedOutput=choices[int(data['label'])])
            goldens.append(golden)
        return goldens


#############################
######## Example Usage ######
#############################

benchmark = HellaSwag(tasks=[HellaSwagTask.TRIMMING_BRANCHES_OR_HEDGES, HellaSwagTask.BATON_TWIRLING], n_shots=0)
results = benchmark.evaluate(model=GPTModel())
print(results)
print(benchmark.score)
print(benchmark.predictions)
print(benchmark.task_scores)