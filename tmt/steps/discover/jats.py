import os
import fmf
import tmt
import click
import shutil
import tmt.steps.discover
import yaml

from tmt import utils


class DiscoverJats(tmt.steps.discover.DiscoverPlugin):
    """
    Use provided list of shell script tests

    List of test cases to be executed can be defined manually directly
    in the plan as a list of dictionaries containing test name, actual
    test script and optionally a path to the test. Example config:

    discover:
        how: jats
        tests:
        - name: /help/main
          test: tmt --help
        - name: /help/test
          test: tmt test --help
        - name: /help/smoke
          test: ./smoke.sh
          path: /tests/shell
    """

    # Supported methods
    _methods = [tmt.steps.Method(name='jats', doc=__doc__, order=60)]

    def show(self):
        """ Show config details """
        super().show([])

    def wake(self):
        # Process command line options, apply defaults
        filters_from_plan = self.get('filter')
        self.data['filter'] = utils.listify(tmt.base.Test._opt('filters') or filters_from_plan)
        self._tests = []

    def go(self):
        """ Discover available tests """
        super(DiscoverJats, self).go()
        if self.get('local_dir'):
            repo_dir = os.path.join(self.get('local_dir'))
        elif self.get('url'):
            url = self.get('url')
            repo_dir = os.path.join(self.workdir, self.get('name'))
            self.info('url', url, 'green')
            self.debug(f"Clone '{url}' to '{repo_dir}'.")
            self.run(
                ['git', 'clone', url, repo_dir],
                shell=False, env={"GIT_ASKPASS": "echo"})
        else:
            raise NotImplementedError('Jats repo has to be specified with local_dir, can not run without this')

        directory = self.step.plan.run.tree.root
        test_path = '/tests/tests/jats'

        def _search_dir(test_dir, res):
            # check for actual test
            if os.path.isfile(os.path.join(test_dir, 'test')):
                data = {}
                test_suite, test_name = test_dir.split("/src/")
                test_suite = test_suite.rsplit(os.path.sep)[-1].strip('jats-')
                test_name = test_name.lstrip(os.path.sep)
                # the test is there, no more subdir searching
                # if main.fmf with test params is present - add it to the test description
                main_fmf = os.path.join(test_dir, 'main.fmf')
                jats_testdata = {}
                if os.path.isfile(main_fmf):
                    with open(main_fmf) as f:
                        jats_testdata = yaml.load(f, Loader=yaml.FullLoader)
                # generate data for the tmt test
                data['duration'] = jats_testdata.get('duration', jats_testdata.get('timeout', '15m'))
                data['summary'] = f"Run jats-{test_suite} {test_name} tests"
                data['test'] = 'bash ./test.sh'
                data['path'] = test_path
                data['framework'] = 'shell'
                data['environment'] = {'TESTSUITE': test_suite, 'TESTNAME': test_name}
                data['tier'] = test_name.split(os.path.sep)[0]
                data['name'] = f"/integration/{test_suite}/{test_name}"
                res.append(data)
            else:
                dirs = [os.path.join(test_dir, f) for f in os.listdir(test_dir)
                        if os.path.isdir(os.path.join(test_dir, f)) and not f.startswith('.') and
                        not f.startswith('_')]
                for a_dir in dirs:
                    _search_dir(a_dir, res)
            return res

        tests_data = _search_dir(os.path.join(repo_dir, 'src'), [])
        # apply filters
        filters = self.get('filter', [])
        tests_data = [t for t in tests_data
                      if all([fmf.utils.filter(a_filter, t, regexp=True) for a_filter in filters])]
        if not tests_data:
            # No tests to run - nothing to do here
            return
        # create tmt workdir
        test_path = os.path.join(self.workdir, test_path.lstrip('/'))
        os.makedirs(test_path)
        # copy test.sh script
        test_sh = os.path.join(directory, 'tests/jats', 'test.sh')
        shutil.copyfile(test_sh, os.path.join(test_path, 'test.sh'))
        # create tmt Test objects
        self._tests = [tmt.Test(data=test, name=test.pop('name')) for test in tests_data]

    def tests(self):
        return self._tests
