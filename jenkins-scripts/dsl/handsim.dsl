import _configs_.*
import javaposse.jobdsl.dsl.Job

def ci_distro = 'trusty'

def supported_distros = [ 'trusty' ]
def supported_arches = [ 'amd64' ]

def handsim_packages = [ 'handsim', 'haptix-comm' ]

// --------------------------------------------------------------
// 1. Create the bundler job
def bundler_job = job("handsim-offline_bundler-builder")
OSRFLinuxBase.create(bundler_job)

bundler_job.with
{
   // Script made to run in the same machine that package repo
   label "master"

   wrappers {
        preBuildCleanup()
   }

   logRotator {
        artifactNumToKeep(2)
   }

   steps {
    shell("""\
          #!/bin/bash -xe

          /bin/bash -x ./scripts/jenkins-scripts/handsim-bundler.bash
          """.stripIndent())
   }
}

// LINUX
handsim_packages.each { pkg ->

  def pkg_name = "${pkg}"

  if ("${pkg_name}" == "haptix-comm")
  {
    pkg_name = "haptix_comm"
  }

  // --------------------------------------------------------------
  // debbuilder jobs
  def build_pkg_job = job("${pkg_name}-debbuilder")
  OSRFLinuxBuildPkg.create(build_pkg_job)
  build_pkg_job.with
  {
    steps {
      shell("""\
            #!/bin/bash -xe

            /bin/bash -x ./scripts/jenkins-scripts/docker/multidistribution-no-ros-debbuild.bash
            """.stripIndent())
    }

    publishers 
    {
      downstreamParameterized {
        trigger("${pkg_name}-install-pkg-${ci_distro}-amd64") {
          condition('SUCCESS')
          parameters {
            currentBuild()
          }
        }
      }
    }
  }

  supported_distros.each { distro ->
    supported_arches.each { arch ->
      // --------------------------------------------------------------
      // 1. Create the default ci jobs
      def handsim_ci_job = job("${pkg_name}-ci-default-${distro}-${arch}")
      OSRFLinuxCompilation.create(handsim_ci_job)

      handsim_ci_job.with
      {
          if ("${pkg}" == 'handsim')
          {
            label "gpu-reliable-${distro}"
          }

          scm {
            hg("http://bitbucket.org/osrf/${pkg}") {
              branch('default')
              subdirectory("${pkg}")
            }
          }

          triggers {
            scm('*/5 * * * *')
          }

          steps {
            shell("""#!/bin/bash -xe

                  export DISTRO=${distro}
                  export ARCH=${arch}

                  /bin/bash -xe ./scripts/jenkins-scripts/docker/${pkg}-compilation.bash
                  """.stripIndent())
          }
      }
   
      // --------------------------------------------------------------
      // 2. Create the ANY job
      def handsim_ci_any_job = job("${pkg_name}-ci-pr_any-${distro}-${arch}")
      OSRFLinuxCompilationAny.create(handsim_ci_any_job,
                                    "http://bitbucket.org/osrf/${pkg}")
      handsim_ci_any_job.with
      {
          if ("${pkg}" == 'handsim')
          {
            label "gpu-reliable-${distro}"
          }

          steps 
          {
            shell("""\
                  export DISTRO=${distro}
                  export ARCH=${arch}

                  /bin/bash -xe ./scripts/jenkins-scripts/docker/${pkg}-compilation.bash
                  """.stripIndent())
          }
      }
    }
  }
}

// LINUX (only handsim) 
supported_distros.each { distro ->
  supported_arches.each { arch ->
    // --------------------------------------------------------------
    // 1. Testing online installation
    def install_default_job = job("handsim-install-pkg-${distro}-${arch}")

    // Use the linux install as base
    OSRFLinuxInstall.create(install_default_job)

    install_default_job.with
    {
       triggers {
          cron('@daily')
       }

        steps {
          shell("""#!/bin/bash -xe

                export INSTALL_JOB_PKG=handsim
                export INSTALL_JOB_REPOS=stable
                /bin/bash -x ./scripts/jenkins-scripts/docker/generic-install-test-job.bash
                """.stripIndent())
       }
    }


    // --------------------------------------------------------------
    // 2. Offline tester
    def unbundler_job = job("handsim-install-offline_bundler-${distro}-${arch}")

    // Use the linux install as base
    OSRFLinuxInstall.create(unbundler_job)

    unbundler_job.with
    {
      parameters
      {
        stringParam('INSTALLED_BUNDLE','',
          'Bundle zip filename to be installed in the system. It is used as base to simulate an update on top of it')
        stringParam('UPDATE_BUNDLE','',
          'Bundle zip filename which will update INSTALLED_BUNDLE in the system')
      }

      steps
      {
        shell("""#!/bin/bash -xe

              /bin/bash -x ./scripts/jenkins-scripts/docker/handsim-install_offline_bundle-test-job.bash
              """.stripIndent())
      }
    }
  }
}

// --------------------------------------------------------------
// WINDOWS

// 1. any for haptix
def haptix_win_ci_any_job = job("haptix_comm-ci-pr_any-windows7-amd64")
OSRFWinCompilationAny.create(haptix_win_ci_any_job,
                              "http://bitbucket.org/osrf/haptix-comm")
haptix_win_ci_any_job.with
{
    steps {
      batchFile("""\
            call "./scripts/jenkins-scripts/haptix_comm-default-devel-windows-amd64.bat"
            """.stripIndent())
    }
}

def haptix_win_ci_job = job("haptix_comm-ci-default-windows7-amd64")
OSRFWinCompilation.create(haptix_win_ci_job)

haptix_win_ci_job.with
{
    scm {
      hg("http://bitbucket.org/osrf/hpatix-comm") {
        branch('default')
        // in win use ign-math to match OSRFWinCompilationAny mechanism
        subdirectory("haptix-comm")
      }
    }

    triggers {
      scm('@daily')
    }

    steps {
      batchFile("""\
            call "./scripts/jenkins-scripts/haptix_comm-default-devel-windows-amd64.bat"
            """.stripIndent())
    }
}
